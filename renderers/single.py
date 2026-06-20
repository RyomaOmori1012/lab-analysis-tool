import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib
import matplotlib.transforms as transforms
import matplotlib.ticker as ticker
import itertools
import io
import re
import warnings
import unicodedata
import json
import base64

warnings.filterwarnings('ignore')

from utils import calc_error, run_statistical_test, parse_text

# --- フォントのグローバル設定 ---
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'MS PGothic', 'IPAexGothic']
plt.rcParams['mathtext.fontset'] = 'custom'
plt.rcParams['mathtext.rm'] = 'Arial'
plt.rcParams['mathtext.it'] = 'Arial:italic'
plt.rcParams['mathtext.bf'] = 'Arial:bold'

def fix_svg_font(svg_bytes):
    svg_str = svg_bytes.getvalue().decode('utf-8')
    svg_str = re.sub(r'font-family:[^;"]+', 'font-family: Arial', svg_str)
    return svg_str.encode('utf-8')

def embed_state_in_svg(svg_bytes):
    try:
        svg_str = svg_bytes.decode('utf-8')
        safe_state = {}
        for k, v in st.session_state.items():
            if k == "svg_uploader": continue
            try:
                json.dumps(v)
                safe_state[k] = v
            except:
                pass
        json_str = json.dumps(safe_state)
        b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        metadata = f'<metadata id="app-state-data">{b64_str}</metadata>'
        svg_str = svg_str.replace('</svg>', f'\n{metadata}\n</svg>')
        return svg_str.encode('utf-8')
    except:
        return svg_bytes

# ★ 修正：隣り合う文字の実際の長さを個別に測り、1文字分の隙間を判定する完璧なロジック
def calc_rotation(labels, xs, font_size, fig_width, x_span):
    if len(xs) < 2 or not labels or len(xs) != len(labels): return 0
    
    # X座標とラベルをペアにして左から順に並べる
    pairs = sorted(zip(xs, labels), key=lambda item: item[0])
    
    def get_text_width(text):
        w = 0
        for c in str(text):
            # 半角英数は細いので0.55としてリアルな幅を計算
            w += 1.0 if unicodedata.east_asian_width(c) in 'FWA' else 0.55
        return w
        
    char_width_inch = font_size / 72.0
    axes_width_inch = fig_width * 0.8
    
    # 全ての隣り合うペアを順番にチェック
    for i in range(len(pairs) - 1):
        x1, lbl1 = pairs[i]
        x2, lbl2 = pairs[i+1]
        
        if x2 - x1 <= 1e-5: continue # 同じ場所ならスキップ
        
        # 2点間の物理的な距離（インチ）
        dx_inch = ((x2 - x1) / x_span) * axes_width_inch
        
        # 2つの文字が中心からお互いに向かって伸びてくる長さ（インチ）
        w1_inch = get_text_width(lbl1) * char_width_inch
        w2_inch = get_text_width(lbl2) * char_width_inch
        occupied_inch = (w1_inch / 2.0) + (w2_inch / 2.0)
        
        # 実際の隙間
        space_inch = dx_inch - occupied_inch
        
        # 隙間が1文字分未満なら斜め書きに判定して終了
        if space_inch < (char_width_inch * 1.0):
            return 45
            
    return 0

def render_single_target(input_data, config):
    if config.get('svg_font_path', True):
        plt.rcParams['svg.fonttype'] = 'path'
    else:
        plt.rcParams['svg.fonttype'] = 'none'

    upper_labels, lower_labels, internal_ids, raw_processed = [], [], [], {}
    dropped_warnings, non_param_warnings, exclude_flags = set(), set(), []
    
    for idx, item in enumerate(input_data):
        u, d, val_t_list, val_l_list = item[0], item[1], item[2], item[3] if len(item) > 3 else []
        exclude_flag = item[4] if len(item) > 4 else False
        exclude_flags.append(exclude_flag)
        
        if config['is_microscope']: raw_processed[f"C_{idx}"] = parse_text(val_t_list[0])
        else:
            t_nums, l_nums = parse_text(val_t_list[0]), parse_text(val_l_list[0])
            length = max(len(t_nums), len(l_nums))
            t_nums.extend([np.nan] * (length - len(t_nums)))
            l_nums.extend([np.nan] * (length - len(l_nums)))
            
            processed = []
            for t, l in zip(t_nums, l_nums):
                if np.isnan(t) or np.isnan(l): processed.append(np.nan)
                elif config['is_qpcr']: processed.append(t - l)
                else: processed.append(np.nan if l == 0 else t / l)
            raw_processed[f"C_{idx}"] = processed
        
        upper_labels.append(u or f"U_{idx+1}")
        lower_labels.append(d or "")
        internal_ids.append(f"C_{idx}")
    
    if not any(len([v for v in raw_processed[uid] if not np.isnan(v)]) > 0 for uid in internal_ids): st.stop()
        
    final_norm = {}
    ctrl_id = internal_ids[0]
    for i, uid in enumerate(internal_ids):
        c_id = internal_ids[lower_labels.index(lower_labels[i])] if 'グループ' in config['norm_mode'] else ctrl_id
        c_mean = np.nanmean(raw_processed[c_id])
        if np.isnan(c_mean) or c_mean == 0: c_mean = 1.0 
        
        if config['is_qpcr']: final_norm[uid] = [2 ** -(v - c_mean) for v in raw_processed[uid]]
        else: final_norm[uid] = [v / c_mean for v in raw_processed[uid]]
    
    p_pairs, test_desc_flat = [], ""
    groupings = [[u for u in internal_ids if lower_labels[internal_ids.index(u)] == low] for low in sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))] if config['is_grouped_test'] else [internal_ids]

    for grp in groupings:
        valid_uids, valid_data = [], []
        for u in grp:
            if exclude_flags[internal_ids.index(u)]: continue
            non_nan_data = [v for v in raw_processed[u] if not np.isnan(v)]
            if len(non_nan_data) >= 2:
                valid_uids.append(u); valid_data.append(non_nan_data)
            else:
                uid_idx = internal_ids.index(u)
                dropped_warnings.add(f"{upper_labels[uid_idx]} ({lower_labels[uid_idx]})" if lower_labels[uid_idx] else upper_labels[uid_idx])
        
        if len(valid_data) < 2: continue
        if config['is_non_param'] and any(len(d) <= 3 for d in valid_data): non_param_warnings.add("解析データ")
        
        if config.get('show_stats', True):
            _, pairs, t_name = run_statistical_test(valid_data, config['var_equal'], config['is_vs_control'], config['is_non_param'], config['is_paired'])
            if t_name: test_desc_flat = t_name
            for i_idx, j_idx, p_val in pairs: p_pairs.append((valid_uids[i_idx], valid_uids[j_idx], p_val))

    if dropped_warnings: st.warning(f"⚠️ データ不足により除外: {', '.join(dropped_warnings)}")
    if non_param_warnings: st.info("💡 n≤3の場合、ノンパラメトリック検定で有意差が出ない可能性があります。")

    unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
    unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
    
    if config['color_mode'] == "色分け":
        cmap = plt.get_cmap('Greys_r')
        if len(unique_up) == 1: colors = [cmap(0.2)]
        else: colors = [cmap(i) for i in np.linspace(0.1, 0.6, len(unique_up))]
        palette = {u: colors[i] for i, u in enumerate(unique_up)}
    else:
        palette = {u: "black" for u in unique_up}
    
    x_coords, bar_width = {}, config['bar_width']
    bar_gap = config.get('bar_gap', 0.02)
    group_gap = config.get('group_gap', 0.50)
    
    if config['layout_mode'] == "条件ごとにグループ化":
        current_x = 0
        for low in unique_low:
            members = [i for i, l in enumerate(lower_labels) if l == low]
            for idx_m, i in enumerate(members):
                x_coords[internal_ids[i]] = current_x
                if idx_m < len(members) - 1:
                    current_x += bar_width + bar_gap
                else:
                    current_x += bar_width + group_gap
    else:
        current_x = 0
        for i, uid in enumerate(internal_ids): 
            x_coords[uid] = current_x
            current_x += bar_width + bar_gap

    x_vals = list(x_coords.values())
    if x_vals:
        max_gap = bar_gap if bar_gap > 0.6 else 0.6
        x_min_val = min(x_vals) - max_gap
        x_max_val = max(x_vals) + max_gap
        x_span = x_max_val - x_min_val
    else:
        x_span = 1.0

    fw = config.get('fig_width', 0.0)
    if fw <= 0:
        fw = max(4.0, len(internal_ids) * 0.8 + x_span * 1.0)
        
    fig_h = config.get('fig_height', 5.0)
    fig, ax = plt.subplots(figsize=(fw, fig_h))
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')

    if config['is_microscope']:
        box_data_safe = [[v for v in final_norm[uid] if not np.isnan(v)] or [np.nan] for uid in internal_ids]
        ax.boxplot(box_data_safe, positions=[x_coords[uid] for uid in internal_ids], widths=bar_width*1.5, patch_artist=True, 
                   boxprops=dict(facecolor='white', color='black', linewidth=1.2), 
                   capprops=dict(color='black', linewidth=1.2), whiskerprops=dict(color='black', linewidth=1.2),
                   medianprops=dict(color='black', linewidth=1.5), flierprops=dict(marker='o', markerfacecolor='black', markeredgecolor='black', alpha=0.8, markersize=4))
    else:
        for i, uid in enumerate(internal_ids):
            mean_val, err_val = np.nanmean(final_norm[uid]), calc_error(final_norm[uid], config['error_bar_type'])
            label_name = upper_labels[i] if i == upper_labels.index(upper_labels[i]) else ""
            ax.bar(x_coords[uid], mean_val if not np.isnan(mean_val) else 0, yerr=err_val if not np.isnan(err_val) else 0, 
                   width=bar_width, color=palette[upper_labels[i]], edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), label=label_name)

    for spine in ax.spines.values(): spine.set_visible(True); spine.set_color('black'); spine.set_linewidth(1.5)
    
    base_fs = config.get('tick_fontsize', 14)
    x_lbl_fs = config.get('x_label_fontsize', 14)
    x_fs_ratio = (x_lbl_fs / 14.0) * (5.0 / fig_h)
    
    ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=base_fs)
    ax.tick_params(axis='x', bottom=False, top=False); ax.set_xticklabels([]) 
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        xs_low = []
        lbls_low = []
        for low in unique_low:
            xs_t = [x_coords[internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
            if xs_t: 
                xs_low.append(sum(xs_t)/len(xs_t))
                lbls_low.append(low)
        rot = calc_rotation(lbls_low, xs_low, x_lbl_fs, fw, x_span)
        
        y_pos = -0.030 * x_fs_ratio
        va_val = 'top'
        if rot > 0:
            max_len = max([len(str(l)) for l in unique_low if l]) if unique_low else 0
            extra_margin = max_len * 0.013 * x_fs_ratio
            y_pos = -0.030 * x_fs_ratio - extra_margin
            va_val = 'center'
            
        for low in unique_low:
            xs = [x_coords[internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
            if xs: ax.text(sum(xs) / len(xs), y_pos, low, ha='center', va=va_val, rotation=rot, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black')
    else:
        xs_up = [x_coords[uid] for uid in internal_ids]
        rot_up = calc_rotation(upper_labels, xs_up, x_lbl_fs, fw, x_span)
        
        y_up = -0.015 * x_fs_ratio
        va_up = 'top'
        extra_margin_up = 0
        if rot_up > 0:
            max_up_len = max([len(str(u)) for u in upper_labels if u]) if upper_labels else 0
            extra_margin_up = max_up_len * 0.013 * x_fs_ratio
            y_up = -0.015 * x_fs_ratio - extra_margin_up
            va_up = 'center'
            
        if rot_up == 0: 
            y_line = y_up - 0.075 * x_fs_ratio 
        else:
            y_line = y_up - extra_margin_up - 0.015 * x_fs_ratio
        
        for i, uid in enumerate(internal_ids):
            ax.text(x_coords[uid], y_up, upper_labels[i], ha='center', va=va_up, rotation=rot_up, transform=trans, fontsize=x_lbl_fs, color='black', fontweight='bold')
            
        xs_low_center = []
        low_labels_clean = []
        for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
            if not label: continue
            xs = [x_coords[internal_ids[x[0]]] for x in elements]
            xs_low_center.append((min(xs) + max(xs)) / 2)
            low_labels_clean.append(label)
            
        rot_low = calc_rotation(low_labels_clean, xs_low_center, x_lbl_fs, fw, x_span)
        va_low = 'top'
        y_low = y_line - 0.015 * x_fs_ratio
        
        if rot_low > 0:
            max_low_len = max([len(str(l)) for l in lower_labels if l]) if lower_labels else 0
            extra_margin_low = max_low_len * 0.013 * x_fs_ratio
            y_low = y_line - 0.015 * x_fs_ratio - extra_margin_low
            va_low = 'center'
            
        for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
            if not label: continue
            xs = [x_coords[internal_ids[x[0]]] for x in elements]
            x_start, x_end = min(xs), max(xs)
            if x_start != x_end: ax.plot([x_start - bar_width/2.5, x_end + bar_width/2.5], [y_line, y_line], color='black', lw=1.2, transform=trans, clip_on=False)
            ax.text((x_start + x_end) / 2, y_low, label, ha='center', va=va_low, rotation=rot_low, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black')

    all_vals = [v for vals in final_norm.values() for v in vals if not np.isnan(v)]
    current_max_y = max(all_vals + [0]) if all_vals else 1.0
    for uid in internal_ids:
        m, e = np.nanmean(final_norm[uid]), calc_error(final_norm[uid], config['error_bar_type'])
        if not np.isnan(m) and not np.isnan(e): current_max_y = max(current_max_y, m + e)
    if current_max_y == 0: current_max_y = 1.0
    
    y_shift, h, base_bracket_y, max_element_y = current_max_y * 0.15, current_max_y * 0.025, current_max_y * 1.10, current_max_y
    levels, max_level, sig_pairs, plotted_stars = [], 0, [], set()
    
    for u1, u2, p in p_pairs:
        if p >= 0.05 or np.isnan(p) or u1 not in x_coords or u2 not in x_coords: continue
        sig_pairs.append((min(x_coords[u1], x_coords[u2]), max(x_coords[u1], x_coords[u2]), "***" if p < 0.001 else "**" if p < 0.01 else "*"))
    
    for x_start, x_end, stars in sorted(sig_pairs, key=lambda x: x[1] - x[0]):
        plotted_stars.add(stars)
        placed_level = next((l_idx for l_idx, intervals in enumerate(levels) if not any(not (x_end < s or x_start > e) for s, e in intervals)), -1)
        if placed_level == -1: placed_level = len(levels); levels.append([])
        levels[placed_level].append((x_start, x_end)); max_level = max(max_level, placed_level)
        by = base_bracket_y + placed_level * y_shift; max_element_y = max(max_element_y, by + h)
        ax.plot([x_start, x_start, x_end, x_end], [by - h, by, by, by - h], color='black', lw=1.2)
        ax.text((x_start + x_end) / 2, by + h*0.2, stars, ha='center', va='bottom', color='black', fontsize=base_fs, fontweight='bold')

    ax.set_ylim(0, max(current_max_y * 1.2, max_element_y * 1.15))
    
    if config.get('y_tick_interval', 0) > 0:
        ax.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
    else:
        ax.yaxis.set_major_locator(ticker.AutoLocator())
        
    if x_vals: 
        ax.set_xlim(x_min_val, x_max_val)
        
    ax.set_ylabel(config['ylabel_input'], fontsize=config.get('label_fontsize', 16), fontweight="bold", color='black', labelpad=10)
    
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label: ax.legend(by_label.values(), by_label.keys(), loc='upper left', bbox_to_anchor=(1.02, 1.0), frameon=False, prop={'size': config.get('legend_fontsize', 12), 'weight': 'bold'})

    n_list = [len([v for v in raw_processed[u] if not np.isnan(v)]) for u in internal_ids]
    expected_n = n_list[0] if n_list and len(set(n_list)) == 1 else "varies"
    star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
    title_str = f"{test_desc_flat}{star_str}" if config['is_microscope'] else f"{test_desc_flat}{star_str}, n={expected_n}" if test_desc_flat else f"n={expected_n}"
    
    if not config.get('show_stats', True): title_str = f"n={expected_n}"
    if title_str: ax.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=15, loc='right')

    st.pyplot(fig)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        err_label = "SEM" if "SEM" in config['error_bar_type'] else "SD"
        
        summary_df = pd.DataFrame({'上段ラベル': upper_labels, '下段ラベル': lower_labels, '平均': [np.nanmean(final_norm[u]) for u in internal_ids], err_label: [calc_error(final_norm[u], config['error_bar_type']) for u in internal_ids]})
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        pd.DataFrame([{"条件名": f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i], "正規化データ": float(val)} for i, u in enumerate(internal_ids) for val in final_norm[u] if not np.isnan(val)]).to_excel(writer, sheet_name='Normalized_Data', index=False)
        
        stat_data = []
        for u1, u2, p in p_pairs:
            idx1, idx2 = internal_ids.index(u1), internal_ids.index(u2)
            c1 = f"{upper_labels[idx1]} ({lower_labels[idx1]})" if lower_labels[idx1] else upper_labels[idx1]
            c2 = f"{upper_labels[idx2]} ({lower_labels[idx2]})" if lower_labels[idx2] else upper_labels[idx2]
            stat_data.append({"比較": f"{c1} vs {c2}", "p値": p if not np.isnan(p) else "N/A", "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns" if not np.isnan(p) else "N/A"})
        if stat_data: pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)

    col_dl1, col_dl2 = st.columns(2)
    buf_svg = io.BytesIO()
    fig.savefig(buf_svg, format='svg', bbox_inches='tight')
    fixed_svg = fix_svg_font(buf_svg)
    final_svg = embed_state_in_svg(fixed_svg)
    
    with col_dl1: st.download_button("📥 Excelデータをダウンロード", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
    with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", final_svg, "Graph.svg", "image/svg+xml", use_container_width=True)
