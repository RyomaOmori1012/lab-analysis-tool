import streamlit as st
import pandas as pd
import numpy as np
import re
from scipy.stats import t
from utils import parse_plate

def run_grubbs_test(values, alpha=0.05):
    """スミルノフ・グラブス検定による外れ値検出（複数検出対応の再帰ループ版）"""
    outlier_indices = []
    # 生データを書き換えないようにコピーを作成
    current_values = list(values)
    
    while True:
        # 有効な（NaNではない）データの数をカウント
        valid_count = sum(1 for v in current_values if not np.isnan(v))
        if valid_count < 3: 
            break # 3つ未満なら検定できないので終了
        
        mean = np.nanmean(current_values)
        std = np.nanstd(current_values, ddof=1)
        
        if std == 0: 
            break # 分散がない（全て同じ値）場合は終了
        
        abs_dev = [abs(v - mean) if not np.isnan(v) else 0 for v in current_values]
        max_idx = np.argmax(abs_dev)
        
        if np.isnan(current_values[max_idx]): 
            break
        
        g_stat = abs_dev[max_idx] / std
        
        # 有効データ数(valid_count)に基づいた棄却域の計算
        p_val = alpha / (2 * valid_count)
        t_val = t.ppf(1 - p_val, valid_count - 2)
        g_crit = ((valid_count - 1) / np.sqrt(valid_count)) * np.sqrt((t_val**2) / (valid_count - 2 + t_val**2))
        
        if g_stat > g_crit:
            # 外れ値として記録
            outlier_indices.append(max_idx)
            # 見つかった外れ値をNaNにして（一時除外して）、次のループへ（再帰的検定）
            current_values[max_idx] = np.nan
        else:
            # 外れ値がもう見つからなければループを抜ける
            break
            
    return outlier_indices

def render_outlier_ui(p_data, plate_idx, config, valid_rows, i_cols, b_cols, c_cols, m_cols, s_cols):
    """外れ値の検出UIを描画し、除外対象のセットを返す"""
    if not p_data.strip() or config.get('mtt_outlier_mode', 'オフ') == 'オフ':
        return set()
        
    arr = parse_plate(p_data)
    alpha = 0.01 if '0.01' in config['mtt_outlier_mode'] else 0.05
    
    outlier_wells = set()
    outlier_options = []
    
    # 全てのデータ列に対して検定を実行
    all_target_cols = set(b_cols + c_cols + m_cols + s_cols)
    for col in all_target_cols:
        if col in i_cols: continue
        row_vals = [arr[r, col] for r in valid_rows]
        clean_vals = [v for v in row_vals if not np.isnan(v)]
        
        if len(clean_vals) >= 3:
            outlier_indices = run_grubbs_test(row_vals, alpha=alpha)
            for idx_in_valid in outlier_indices:
                r = valid_rows[idx_in_valid]
                w_name = f"{chr(65+r)}{col+1}"
                val_raw = arr[r, col]
                outlier_wells.add((r, col))
                outlier_options.append(f"{w_name}ウェル (値: {val_raw:.4f})")
    
    # 表の描画
    st.markdown("<span style='font-size:0.85em; font-weight:bold; color:#4ade80;'>👁️ プレートデータ状態（赤字：外れ値候補）</span>", unsafe_allow_html=True)
    df_grid = pd.DataFrame(arr, index=[chr(65+r) for r in range(8)], columns=[str(c+1) for c in range(12)])
    
    def style_outliers(df):
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        for r, c in outlier_wells:
            styles.iloc[r, c] = 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
        return styles
        
    st.dataframe(df_grid.style.apply(style_outliers, axis=None), use_container_width=True)
    
    # 選択UI
    active_excludes = set()
    if outlier_options:
        sel_excluded = st.multiselect(f"🚨 除外したい外れ値にチェックを入れてください:", options=outlier_options, key=f"mtt_sel_outliers_{plate_idx}")
        for s in sel_excluded:
            w_match = re.match(r"([A-H])([0-9]+)", s)
            if w_match:
                r_idx = ord(w_match.group(1)) - 65
                c_idx = int(w_match.group(2)) - 1
                active_excludes.add((r_idx, c_idx))
                
    return active_excludes