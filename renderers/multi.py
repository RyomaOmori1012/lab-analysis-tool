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

def get_font(text):
    return 'sans-serif'

def fix_svg_font(svg_bytes):
    svg_str = svg_bytes.getvalue().decode('utf-8')
    svg_str = re.sub(r'font-family:[^;"]+', 'font-family: Arial, "MS PGothic", "IPAexGothic", sans-serif', svg_str)
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

def calc_rotation(labels, xs, font_size, fig_width, x_span):
    if len(xs) < 2 or not labels or len(xs) != len(labels): return 0
    pairs = sorted(zip(xs, labels), key=lambda item: item[0])
    
    def get_text_width(text):
        w = 0
        for c in str(text):
            w += 1.0 if unicodedata.east_asian_width(c) in 'FWA' else 0.55
        return w
        
    char_width_inch = font_size / 72.0
    axes_width_inch = fig_width * 0.8
    
    for i in range(len(pairs) - 1):
        x1, lbl1 = pairs[i]
        x2, lbl2 = pairs[i+1]
        if x2 - x1 <= 1e-5: continue
        dx_inch = ((x2 - x1) / x_span) * axes_width_inch
        w1_inch = get_text_width(lbl1) * char_width_inch
        w2_inch = get_text_width(lbl2) * char_width_inch
        occupied_inch = (w1_inch / 2.0) + (w2_inch / 2.0)
        space_inch = dx_inch - occupied_inch
        if space_inch < (char_width_inch * 1.0):
            return 45
    return 0

def draw_x_labels(ax, config, internal_ids, upper_labels, lower_labels, x_coords_multi, fw, x_span, bar_width):
    x_lbl_fs = config.get('x_label_fontsize', 14)
    fig_h = config.get('fig_height', 5.5)
    x_fs_ratio = (x_lbl_fs / 14.0) * (5.5 / fig_h)
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    
    ax.tick_params(axis='x', bottom=False, top=False)
    ax.set_xticks([])
    ax.set_xticklabels([])
    
    global_lowest_y = 0
    # 下段ラベルが1つでも存在するかチェック
    has_lower = any(l for l in lower_labels if l)
    
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        unique_low = sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))
        all_xs_low, all_lbls_low = [], []
        for j in range(config['num_targets']):
            for low in unique_low:
                xs_t = [x_coords_multi[j][internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
                if xs_t: 
                    all_xs_low.append(sum(xs_t)/len(xs_t))
                    all_lbls_low.append(low)
                    
        rot = calc_rotation(all_lbls_low, all_xs_low, x_lbl_fs, fw, x_span)
        y_pos = -0.015 * x_fs_ratio
        va_val = 'top'
        extra_margin = 0
        if rot > 0:
            max_len = max([len(str(l)) for l in unique_low if l]) if unique_low else 0
            extra_margin = max_len * 0.013 * x_fs_ratio
            y_pos = -0.015 * x_fs_ratio - extra_margin
            va_val = 'center'
            
        for j in range(config['num_targets']):
            for low in unique_low:
                xs = [x_coords_multi[j][internal_ids[i]] for i, l in enumerate(lower_labels) if l == low]
                if xs: ax.text(sum(xs) / len(xs), y_pos, low, ha='center', va=va_val, rotation=rot, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black', fontname=get_font(low))
                
        global_lowest_y = y_pos - (0.015 * x_fs_ratio if rot == 0 else extra_margin)
        
    else:
        # --- 上段ラベルの描画 ---
        all_xs_up, all_lbls_up = [], []
        for j in range(config['num_targets']):
            all_xs_up.extend([x_coords_multi[j][uid] for uid in internal_ids])
            all_lbls_up.extend(upper_labels)
            
        rot_up = calc_rotation(all_lbls_up, all_xs_up, x_lbl_fs, fw, x_span)
        y_up = -0.015 * x_fs_ratio
        va_up = 'top'
        extra_margin_up = 0
        
        if rot_up > 0:
            max_up_len = max([len(str(u)) for u in upper_labels if u]) if upper_labels else 0
            extra_margin_up = max_up_len * 0.013 * x_fs_ratio
            y_up = -0.015 * x_fs_ratio - extra_margin_up
            va_up = 'center'
            
        # single.pyに合わせた y_line (区切り線) の高さ設定
        if rot_up == 0: 
            y_line = y_up - 0.075 * x_fs_ratio 
        else:
            y_line = y_up - extra_margin_up - 0.015 * x_fs_ratio
            
        for j in range(config['num_targets']):
            for i, uid in enumerate(internal_ids):
                ax.text(x_coords_multi[j][uid], y_up, upper_labels[i], ha='center', va=va_up, rotation=rot_up, transform=trans, fontsize=x_lbl_fs, color='black', fontweight='bold', fontname=get_font(upper_labels[i]))
        
        # --- 下段ラベルの描画 (存在する場合のみ) ---
        if has_lower:
            all_xs_low_center, all_low_labels_clean = [], []
            for j in range(config['num_targets']):
                for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
                    if not label: continue
                    xs = [x_coords_multi[j][internal_ids[x[0]]] for x in elements]
                    all_xs_low_center.append((min(xs) + max(xs)) / 2)
                    all_low_labels_clean.append(label)
                    
            rot_low = calc_rotation(all_low_labels_clean, all_xs_low_center, x_lbl_fs, fw, x_span)
            va_low = 'top'
            y_low = y_line - 0.015 * x_fs_ratio
            
            extra_margin_low = 0
            if rot_low > 0:
                max_low_len = max([len(str(l)) for l in lower_labels if l]) if lower_labels else 0
                extra_margin_low = max_low_len * 0.013 * x_fs_ratio
                y_low = y_line - 0.015 * x_fs_ratio - extra_margin_low
                va_low = 'center'
                
            for j in range(config['num_targets']):
                for label, elements in [(k, list(g)) for k, g in itertools.groupby(enumerate(lower_labels), key=lambda x: x[1])]:
                    if not label: continue
                    xs = [x_coords_multi[j][internal_ids[x[0]]] for x in elements]
                    x_start, x_end = min(xs), max(xs)
                    if x_start != x_end: ax.plot([x_start - bar_width/2.5, x_end + bar_width/2.5], [y_line, y_line], color='black', lw=1.2, transform=trans, clip_on=False)
                    ax.text((x_start + x_end) / 2, y_low, label, ha='center', va=va_low, rotation=rot_low, transform=trans, fontsize=x_lbl_fs, fontweight='bold', color='black', fontname=get_font(label))
            
            # ターゲット名を描画する際のベースラインを下段ラベルの下に設定
            global_lowest_y = y_line - 0.075 * x_fs_ratio if rot_low == 0 else y_low - extra_margin_low - 0.015 * x_fs_ratio
        else:
            # 下段がない場合は、ターゲット名を描画するベースラインを上段ラベルのすぐ下に引き上げる
            global_lowest_y = y_line

    # --- ターゲット名（最下段）の描画 ---
    if config['num_targets'] > 1:
        # single.pyの区切り線と同じマージンでターゲット名を配置
        y_tgt = global_lowest_y - 0.015 * x_fs_ratio
        for j in range(config['num_targets']):
            xs_target = list(x_coords_multi[j].values())
            if xs_target:
                x_start, x_end = min(xs_target), max(xs_target)
                c = (x_start + x_end) / 2
                ax.plot([x_start - bar_width/2, x_end + bar_width/2], [global_lowest_y, global_lowest_y], color='black', lw=1.5, transform=trans, clip_on=False)
                ax.text(c, y_tgt, config['target_names'][j], ha='center', va='top', transform=trans, fontsize=x_lbl_fs+2, fontweight='bold', color='black', fontname=get_font(config['target_names'][j]))
                
def render_multi_target(input_data, config):
    if config.get('svg_font_path', True):
        plt.rcParams['svg.fonttype'] = 'path'
    else:
        plt.rcParams['svg.fonttype'] = 'none'

    upper_labels, lower_labels, internal_ids = [], [], []
    raw_processed_multi = {j: {} for j in range(config['num_targets'])}
    dropped_warnings, non_param_warnings, exclude_flags = set(), set(), []
    
    raw_target_data_multi = {j: {} for j in range(config['num_targets'])}
    raw_loading_data_multi = {j: {} for j in range(config['num_targets'])}
    
    for idx, item in enumerate(input_data):
        u, d, val_t_list, val_l_list = item[0], item[1], item[2], item[3] if len(item) > 3 else []
        exclude_flag = item[4] if len(item) > 4 else False
        exclude_flags.append(exclude_flag)
        
        for j in range(config['num_targets']):
            t_nums, l_nums = parse_text(val_t_list[j]), parse_text(val_l_list[j])
            raw_target_data_multi[j][f"C_{idx}"] = list(t_nums)
            raw_loading_data_multi[j][f"C_{idx}"] = list(l_nums)
            
            length = max(len(t_nums), len(l_nums))
            t_nums_ext = t_nums + [np.nan] * (length - len(t_nums))
            l_nums_ext = l_nums + [np.nan] * (length - len(l_nums))
            
            processed = []
            for t, l in zip(t_nums_ext, l_nums_ext):
                if np.isnan(t) or np.isnan(l): processed.append(np.nan)
                elif config['is_qpcr']: processed.append(t - l)
                else: processed.append(np.nan if l == 0 else t / l)
            raw_processed_multi[j][f"C_{idx}"] = processed
                
        upper_labels.append(u or f"U_{idx+1}")
        lower_labels.append(d or "")
        internal_ids.append(f"C_{idx}")
        
    if not any(len([v for v in raw_processed_multi[0][uid] if not np.isnan(v)]) > 0 for uid in internal_ids): st.stop()
    
    final_norm_multi = {j: {} for j in range(config['num_targets'])}
    ctrl_id = internal_ids[0]
    
    for j in range(config['num_targets']):
        for i, uid in enumerate(internal_ids):
            c_id = internal_ids[lower_labels.index(lower_labels[i])] if 'グループ' in config['norm_mode'] else ctrl_id
            c_mean = np.nanmean(raw_processed_multi[j][c_id])
            if np.isnan(c_mean) or c_mean == 0: c_mean = 1.0 
            if config['is_qpcr']: final_norm_multi[j][uid] = [2 ** -(v - c_mean) for v in raw_processed_multi[j][uid]]
            else: final_norm_multi[j][uid] = [v / c_mean for v in raw_processed_multi[j][uid]]
    
    p_pairs_multi = {j: [] for j in range(config['num_targets'])}
    test_desc_flat = ""
    groupings = [[u for u in internal_ids if lower_labels[internal_ids.index(u)] == low] for low in sorted(list(set(lower_labels)), key=lambda x: lower_labels.index(x))] if config['is_grouped_test'] else [internal_ids]

    for j in range(config['num_targets']):
        for grp in groupings:
            valid_uids, valid_data = [], []
            for u in grp:
                if exclude_flags[internal_ids.index(u)]: continue
                non_nan_data = [v for v in raw_processed_multi[j][u] if not np.isnan(v)]
                if len(non_nan_data) >= 2:
                    valid_uids.append(u); valid_data.append(non_nan_data)
                else:
                    uid_idx = internal_ids.index(u)
                    dropped_warnings.add(f"{config['target_names'][j]}の{upper_labels[uid_idx]}")
            
            if len(valid_data) < 2: continue
            if config['is_non_param'] and any(len(d) <= 3 for d in valid_data): non_param_warnings.add("解析データ")
                
            if config.get('show_stats', True):
                _, pairs, t_name = run_statistical_test(valid_data, config['var_equal'], config['is_vs_control'], config['is_non_param'], config['is_paired'])
                if t_name: test_desc_flat = t_name
                for i_idx, j_idx, p_val in pairs: p_pairs_multi[j].append((valid_uids[i_idx], valid_uids[j_idx], p_val))

    if dropped_warnings: st.warning(f"⚠️ データ不足により除外: {', '.join(dropped_warnings)}")
    if non_param_warnings: st.info("💡 n≤3の場合、ノンパラメトリック検定で有意差が出ない可能性があります。")

    unique_up = sorted(list(set(upper_labels)), key=lambda x: upper_labels.index(x))
    
    if config['color_mode'] == "色分け":
        cmap = plt.get_cmap('Greys_r')
        if len(unique_up) == 1: colors = [cmap(0.2)]
        else: colors = [cmap(i) for i in np.linspace(0.1, 0.6, len(unique_up))]
        palette = {u: colors[i] for i, u in enumerate(unique_up)}
    else:
        palette = {u: "black" for u in unique_up}
        
    bar_width, x_coords_multi, target_centers, current_x = config['bar_width'], {j: {} for j in range(config['num_targets'])}, [], 0
    bar_gap = config.get('bar_gap', 0.02)
    group_gap = config.get('group_gap', 0.50)
    
    for j in range(config['num_targets']):
        g_start = current_x
        for i, uid in enumerate(internal_ids):
            x_coords_multi[j][uid] = current_x
            if i < len(internal_ids) - 1:
                current_x += bar_width + bar_gap
            else:
                current_x += bar_width + group_gap
        target_centers.append((g_start + current_x - bar_width - group_gap) / 2)

    x_vals = [x for j in range(config['num_targets']) for x in x_coords_multi[j].values()]
    if x_vals:
        max_gap = bar_gap if bar_gap > 0.6 else 0.6
        x_min_val = min(x_vals) - max_gap
        x_max_val = current_x - group_gap + max_gap
        x_span = x_max_val - x_min_val
    else:
        x_span = 1.0

    fw = config.get('fig_width', 0.0)
    if fw <= 0:
        num_bars_total = config['num_targets'] * len(unique_up)
        fw = max(6.0, num_bars_total * 0.8 + x_span * 1.0)
        
    fig_h = config.get('fig_height', 5.5)
    fig, ax = plt.subplots(figsize=(fw, fig_h))
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')
    
    for j in range(config['num_targets']):
        for i, uid in enumerate(internal_ids):
            cx = x_coords_multi[j][uid]
            mean_val, err_val = np.nanmean(final_norm_multi[j][uid]), calc_error(final_norm_multi[j][uid], config['error_bar_type'])
            label_name = upper_labels[i] if (j == 0 and i == upper_labels.index(upper_labels[i])) else ""
            ax.bar(cx, mean_val if not np.isnan(mean_val) else 0, yerr=err_val if not np.isnan(err_val) else 0, 
                   width=bar_width, color=palette[upper_labels[i]], edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), label=label_name)

    for spine in ax.spines.values(): spine.set_visible(True); spine.set_color('black'); spine.set_linewidth(1.5)
    
    base_fs = config.get('tick_fontsize', 14)
    x_lbl_fs = config.get('x_label_fontsize', 14)
    x_fs_ratio = (x_lbl_fs / 14.0) * (5.5 / fig_h)
    
    ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=base_fs)
    ax.tick_params(axis='x', bottom=False, top=False)
    draw_x_labels(ax, config, internal_ids, upper_labels, lower_labels, x_coords_multi, fw, x_span, bar_width)
    
    
    
    all_vals = [v for j in range(config['num_targets']) for vals in final_norm_multi[j].values() for v in vals if not np.isnan(v)]
    current_max_y = max(all_vals + [0]) if all_vals else 1.0
    for j in range(config['num_targets']):
        for uid in internal_ids:
            m, e = np.nanmean(final_norm_multi[j][uid]), calc_error(final_norm_multi[j][uid], config['error_bar_type'])
            if not np.isnan(m) and not np.isnan(e): current_max_y = max(current_max_y, m + e)
    if current_max_y == 0: current_max_y = 1.0
    
    y_shift, h = current_max_y * 0.15, current_max_y * 0.025
    global_base_bracket_y = current_max_y * 1.10
    max_element_y = current_max_y
    plotted_stars = set()
    
    for j in range(config['num_targets']):
        levels, max_level, sig_pairs = [], 0, []
        base_bracket_y = global_base_bracket_y
        for u1, u2, p in p_pairs_multi[j]:
            if p >= 0.05 or np.isnan(p) or u1 not in x_coords_multi[j] or u2 not in x_coords_multi[j]: continue
            sig_pairs.append((min(x_coords_multi[j][u1], x_coords_multi[j][u2]), max(x_coords_multi[j][u1], x_coords_multi[j][u2]), "***" if p < 0.001 else "**" if p < 0.01 else "*"))
        
        for x_start, x_end, stars in sorted(sig_pairs, key=lambda x: x[1] - x[0]):
            plotted_stars.add(stars)
            placed_level = next((l_idx for l_idx, intervals in enumerate(levels) if not any(not (x_end < s or x_start > e) for s, e in intervals)), -1)
            if placed_level == -1: placed_level = len(levels); levels.append([])
            levels[placed_level].append((x_start, x_end)); max_level = max(max_level, placed_level)
            by = base_bracket_y + placed_level * y_shift; max_element_y = max(max_element_y, by + h)
            ax.plot([x_start, x_start, x_end, x_end], [by - h, by, by, by - h], color='black', lw=1.2)
            ax.text((x_start + x_end) / 2, by, stars, ha='center', va='bottom', color='black', fontsize=base_fs, fontweight='bold')
       
    ax.set_ylim(0, max(current_max_y * 1.2, max_element_y * 1.15))
    
    if config.get('y_tick_interval', 0) > 0:
        ax.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
    else:
        ax.yaxis.set_major_locator(ticker.AutoLocator())
        
    if x_vals: 
        ax.set_xlim(x_min_val, x_max_val)
        
    ax.set_ylabel(config['ylabel_input'], fontsize=base_fs + 2, fontweight="bold", color='black', labelpad=10, fontname=get_font(config['ylabel_input']))
    
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label: 
            leg_font = 'Arial'
            for lbl in by_label.keys():
                if get_font(lbl) == 'IPAexGothic':
                    leg_font = 'IPAexGothic'
                    break
            ax.legend(by_label.values(), by_label.keys(), loc='upper left', bbox_to_anchor=(1.02, 1.0), frameon=False, prop={'size': config.get('legend_fontsize', 12), 'weight': 'bold', 'family': leg_font})

    expected_n = n_list[0] if (n_list := [len([v for v in raw_processed_multi[0][u] if not np.isnan(v)]) for u in internal_ids]) and len(set(n_list)) == 1 else "varies"
    star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
    title_str = f"{test_desc_flat}{star_str}, n={expected_n}" if test_desc_flat else f"n={expected_n}"
    
    if not config.get('show_stats', True): title_str = f"n={expected_n}"
    if title_str: ax.set_title(title_str, fontsize=config.get('title_fontsize', 14), pad=15, loc='right', fontname=get_font(title_str))

    st.pyplot(fig)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        err_label = "SEM" if "SEM" in config['error_bar_type'] else "SD"
        pd.DataFrame([{'ターゲット名': config['target_names'][j], '上段ラベル': upper_labels[i], '下段ラベル': lower_labels[i], '平均': np.nanmean(final_norm_multi[j][u]), err_label: calc_error(final_norm_multi[j][u], config['error_bar_type'])} for j in range(config['num_targets']) for i, u in enumerate(internal_ids)]).to_excel(writer, sheet_name='Summary', index=False)
        
        detailed_rows = []
        for j in range(config['num_targets']):
            for i, uid in enumerate(internal_ids):
                c_title = f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i]
                t_list = raw_target_data_multi[j].get(uid, [])
                l_list = raw_loading_data_multi[j].get(uid, [])
                proc_list = raw_processed_multi[j].get(uid, [])
                norm_list = final_norm_multi[j].get(uid, [])
                
                max_len = max(len(t_list), len(l_list), len(proc_list), len(norm_list))
                for r_idx in range(max_len):
                    row_dict = {"ターゲット名": config['target_names'][j], "条件名": c_title}
                    row_dict["生データ (Target)"] = t_list[r_idx] if r_idx < len(t_list) else np.nan
                    row_dict["生データ (Loading Control)"] = l_list[r_idx] if r_idx < len(l_list) else np.nan
                    calc_name = "計算過程 (Target - Loading)" if config['is_qpcr'] else "計算過程 (Target / Loading)"
                    row_dict[calc_name] = proc_list[r_idx] if r_idx < len(proc_list) else np.nan
                    row_dict["正規化後データ"] = norm_list[r_idx] if r_idx < len(norm_list) else np.nan
                    detailed_rows.append(row_dict)
        pd.DataFrame(detailed_rows).to_excel(writer, sheet_name='Detailed_Data', index=False)

        stat_data = []
        for j in range(config['num_targets']):
            for u1, u2, p in p_pairs_multi[j]:
                idx1, idx2 = internal_ids.index(u1), internal_ids.index(u2)
                c1 = f"{upper_labels[idx1]} ({lower_labels[idx1]})" if lower_labels[idx1] else upper_labels[idx1]
                c2 = f"{upper_labels[idx2]} ({lower_labels[idx2]})" if lower_labels[idx2] else upper_labels[idx2]
                stat_data.append({
                    "ターゲット名": config['target_names'][j], 
                    "比較": f"{c1} vs {c2}", 
                    "p値": p if not np.isnan(p) else "N/A", 
                    "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns" if not np.isnan(p) else "N/A",
                    "検定手法": test_desc_flat,
                    "検定の前提": "ノンパラメトリック" if config.get('is_non_param') else "パラメトリック",
                    "対応の有無": "対応あり" if config.get('is_paired') else "対応なし",
                    "多重比較": "Controlとの比較" if config.get('is_vs_control') else "全ペア総当たり",
                    "エラーバー": config.get('error_bar_type', '設定なし'),
                    "正規化": config.get('norm_mode', '設定なし')
                })
        if stat_data: pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)

    col_dl1, col_dl2 = st.columns(2)
    buf_svg = io.BytesIO()
    fig.savefig(buf_svg, format='svg', bbox_inches='tight')
    fixed_svg = fix_svg_font(buf_svg)
    final_svg = embed_state_in_svg(fixed_svg)
    
    with col_dl1: st.download_button("📥 Excelデータをダウンロード", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
    with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", final_svg, "Graph.svg", "image/svg+xml", use_container_width=True)