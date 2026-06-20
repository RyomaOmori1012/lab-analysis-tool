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

def calc_rotation(labels, xs):
    if len(xs) < 2: return 0
    unique_xs = sorted(list(set(xs)))
    if len(unique_xs) < 2: return 0
    min_dx = min(unique_xs[i+1] - unique_xs[i] for i in range(len(unique_xs)-1))
    max_len = max([len(str(l)) for l in labels if l]) if labels else 0
    if (max_len * 0.04) > min_dx: return 45
    return 0

def render_multi_target(input_data, config):
    if config.get('svg_font_path', True):
        plt.rcParams['svg.fonttype'] = 'path'
    else:
        plt.rcParams['svg.fonttype'] = 'none'

    upper_labels, lower_labels, internal_ids = [], [], []
    raw_processed_multi = {j: {} for j in range(config['num_targets'])}
    dropped_warnings, non_param_warnings, exclude_flags = set(), set(), []
    
    for idx, item in enumerate(input_data):
        u, d, val_t_list, val_l_list = item[0], item[1], item[2], item[3] if len(item) > 3 else []
        exclude_flag = item[4] if len(item) > 4 else False
        exclude_flags.append(exclude_flag)
        
        for j in range(config['num_targets']):
            if config['is_microscope']: raw_processed_multi[j][f"C_{idx}"] = parse_text(val_t_list[j])
            else:
                t_nums, l_nums = parse_text(val_t_list[j]), parse_text(val_l_list[j])
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
        
    fig, ax = plt.subplots(figsize=(max(6.0, config['num_targets'] * len(unique_up) * 1.0), 5.5))
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')
    
    bar_width, x_coords_multi, target_centers, current_x = config['bar_width'], {j: {} for j in range(config['num_targets'])}, [], 0
    bar_gap = config.get('bar_gap', 0.02)
    
    for j in range(config['num_targets']):
        g_start = current_x
        for i, uid in enumerate(internal_ids):
            x_coords_multi[j][uid] = current_x
            if config['is_microscope']:
                d_list_safe = [v for v in final_norm_multi[j][uid] if not np.isnan(v)] or [np.nan]
                ax.boxplot([d_list_safe], positions=[current_x], widths=bar_width*1.5, patch_artist=True, 
                           boxprops=dict(facecolor='white', color='black', linewidth=1.2), capprops=dict(color='black', linewidth=1.2),
                           whiskerprops=dict(color='black', linewidth=1.2), medianprops=dict(color='black', linewidth=1.5), 
                           flierprops=dict(marker='o', markerfacecolor='black', markeredgecolor='black', alpha=0.8, markersize=4))
            else:
                mean_val, err_val = np.nanmean(final_norm_multi[j][uid]), calc_error(final_norm_multi[j][uid], config['error_bar_type'])
                label_name = upper_labels[i] if (j == 0 and i == upper_labels.index(upper_labels[i])) else ""
                ax.bar(current_x, mean_val if not np.isnan(mean_val) else 0, yerr=err_val if not np.isnan(err_val) else 0, 
                       width=bar_width, color=palette[upper_labels[i]], edgecolor='black', capsize=3, error_kw=dict(ecolor='black', lw=1.2), label=label_name)
            current_x += bar_width + bar_gap
        target_centers.append((g_start + current_x - bar_width - bar_gap) / 2)
        current_x += 0.8

    for spine in ax.spines.values(): spine.set_visible(True); spine.set_color('black'); spine.set_linewidth(1.5)
    ax.tick_params(axis='y', colors='black', direction='in', left=True, right=False, length=5, width=1.5, labelsize=14)
    ax.tick_params(axis='x', bottom=False, top=False)
    
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    rot_tgt = calc_rotation(config['target_names'], target_centers)
    
    y_tgt = -0.015
    va_tgt = 'top'
    if rot_tgt > 0:
        max_tgt_len = max([len(str(t)) for t in config['target_names'] if t]) if config['target_names'] else 0
        extra_margin_tgt = max_tgt_len * 0.013
        y_tgt = -0.015 - extra_margin_tgt
        va_tgt = 'center'
        
    ax.set_xticks(target_centers)
    ax.set_xticklabels([])
    for j, c in enumerate(target_centers):
        ax.text(c, y_tgt, config['target_names'][j], ha='center', va=va_tgt, rotation=rot_tgt, transform=trans, fontsize=16, fontweight='bold', color='black')
    
    all_vals = [v for j in range(config['num_targets']) for vals in final_norm_multi[j].values() for v in vals if not np.isnan(v)]
    current_max_y = max(all_vals + [0]) if all_vals else 1.0
    for j in range(config['num_targets']):
        for uid in internal_ids:
            m, e = np.nanmean(final_norm_multi[j][uid]), calc_error(final_norm_multi[j][uid], config['error_bar_type'])
            if not np.isnan(m) and not np.isnan(e): current_max_y = max(current_max_y, m + e)
    if current_max_y == 0: current_max_y = 1.0
    
    y_shift, h, base_bracket_y, max_element_y = current_max_y * 0.15, current_max_y * 0.025, current_max_y * 1.10, current_max_y
    plotted_stars = set()
    
    for j in range(config['num_targets']):
        levels, max_level, sig_pairs = [], 0, []
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
            ax.text((x_start + x_end) / 2, by + h*0.2, stars, ha='center', va='bottom', color='black', fontsize=14, fontweight='bold')
        base_bracket_y += (max_level + 1) * y_shift if sig_pairs else 0
        max_element_y = max(max_element_y, base_bracket_y)

    ax.set_ylim(0, max(current_max_y * 1.2, max_element_y * 1.15))
    
    if config.get('y_tick_interval', 0) > 0:
        ax.yaxis.set_major_locator(ticker.MultipleLocator(config['y_tick_interval']))
    else:
        ax.yaxis.set_major_locator(ticker.AutoLocator())
        
    x_vals = list(x_coords.values())
    if x_vals: 
        max_gap = bar_gap if bar_gap > 0.6 else 0.6
        ax.set_xlim(min(x_vals) - max_gap, current_x - 0.8 + max_gap)
        
    ax.set_ylabel(config['ylabel_input'], fontsize=16, fontweight="bold", color='black', labelpad=10)
    
    # ★ 凡例（系列）をグラフの右側外（上空を避ける）に配置
    if config['label_style'] == "1段 ＋ 系列名（凡例）":
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label: ax.legend(by_label.values(), by_label.keys(), loc='upper left', bbox_to_anchor=(1.02, 1.0), frameon=False, prop={'size': 12, 'weight': 'bold'})

    expected_n = n_list[0] if (n_list := [len([v for v in raw_processed_multi[0][u] if not np.isnan(v)]) for u in internal_ids]) and len(set(n_list)) == 1 else "varies"
    star_str = ", " + ", ".join([f"{s} p < {0.05 if s=='*' else 0.01 if s=='**' else 0.001}" for s in ["*", "**", "***"] if s in plotted_stars]) if plotted_stars else ""
    title_str = f"{test_desc_flat}{star_str}, n={expected_n}" if test_desc_flat else f"n={expected_n}"
    
    if not config.get('show_stats', True): title_str = f"n={expected_n}"
    ax.set_title(title_str, fontsize=14, pad=15, loc='right')

    st.pyplot(fig)
    
    # --- Excel 書き出し ---
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        err_label = "SEM" if "SEM" in config['error_bar_type'] else "SD"
        pd.DataFrame([{'ターゲット名': config['target_names'][j], '上段ラベル': upper_labels[i], '下段ラベル': lower_labels[i], '平均': np.nanmean(final_norm_multi[j][u]), err_label: calc_error(final_norm_multi[j][u], config['error_bar_type'])} for j in range(config['num_targets']) for i, u in enumerate(internal_ids)]).to_excel(writer, sheet_name='Summary', index=False)
        
        ws = writer.book['Summary']
        ws.cell(row=2, column=7, value="💡 【複数ターゲットの棒グラフ最短作成手順】")
        ws.cell(row=3, column=7, value="1. 1行目（見出し）を選択し、[データ]タブ ＞ [フィルター] をクリック。")
        ws.cell(row=4, column=7, value="2. 『ターゲット名』の▼をクリックし、グラフにしたいターゲットを1つだけ選んで絞り込む。")
        ws.cell(row=5, column=7, value="3. 表示された『上段ラベル』と『平均』の列を同時選択し、[挿入] ＞ [縦棒グラフ] を作成。")
        ws.cell(row=6, column=7, value="4. グラフの棒をクリックし、[＋] ＞ [誤差範囲] ＞ [その他の誤差範囲オプション]。")
        ws.cell(row=7, column=7, value=f"5. 『カスタム』を選び、『値の指定』で正負両方に、フィルター後の表示されている『{err_label}』の列をドラッグして指定すれば完成！")

        pd.DataFrame([{"ターゲット名": config['target_names'][j], "条件名": f"{upper_labels[i]} ({lower_labels[i]})" if lower_labels[i] else upper_labels[i], "正規化データ": float(val)} for j in range(config['num_targets']) for i, u in enumerate(internal_ids) for val in final_norm_multi[j][u] if not np.isnan(val)]).to_excel(writer, sheet_name='Normalized_Data', index=False)
        
        stat_data = []
        for j in range(config['num_targets']):
            for u1, u2, p in p_pairs_multi[j]:
                idx1, idx2 = internal_ids.index(u1), internal_ids.index(u2)
                c1 = f"{upper_labels[idx1]} ({lower_labels[idx1]})" if lower_labels[idx1] else upper_labels[idx1]
                c2 = f"{upper_labels[idx2]} ({lower_labels[idx2]})" if lower_labels[idx2] else upper_labels[idx2]
                stat_data.append({"ターゲット名": config['target_names'][j], "比較": f"{c1} vs {c2}", "p値": p if not np.isnan(p) else "N/A", "判定": "***" if p<0.001 else "**" if p<0.01 else "*" if p<0.05 else "ns" if not np.isnan(p) else "N/A"})
        if stat_data: pd.DataFrame(stat_data).to_excel(writer, sheet_name='Statistical_Details', index=False)

    col_dl1, col_dl2 = st.columns(2)
    buf_svg = io.BytesIO()
    fig.savefig(buf_svg, format='svg', bbox_inches='tight')
    fixed_svg = fix_svg_font(buf_svg)
    
    with col_dl1: st.download_button("📥 Excelデータをダウンロード", excel_buffer.getvalue(), "Analysis_Data.xlsx", type="primary", use_container_width=True)
    with col_dl2: st.download_button("📥 完成グラフ(SVG)を保存", fixed_svg, "Graph.svg", "image/svg+xml", use_container_width=True)
