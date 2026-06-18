import streamlit as st
import pandas as pd
import numpy as np
import re
import traceback

from renderers import render_mtt_analysis, render_single_target, render_multi_target

# ==========================================
# グローバル設定
# ==========================================
st.set_page_config(page_title="実験データ自動解析ツール", layout="wide")
st.title("🧪 実験データ自動解析ツール")

st.markdown("""
    <style>
    textarea {
        white-space: pre !important;
        overflow-wrap: normal !important;
        overflow-x: scroll !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# メイン実行関数
# ==========================================
def main():
    # --- サイドバー設定 ---
    st.sidebar.header("⚙️ 全体設定")
    selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'])
    num_cond = st.sidebar.number_input('手動モード時の条件数:', min_value=1, max_value=20, value=2, step=1)

    is_mtt = 'MTT' in selected_exp
    is_microscope = '顕微鏡' in selected_exp
    is_qpcr = 'qPCR' in selected_exp
    is_hplc = 'HPLC' in selected_exp
    is_multi_capable = 'WB' in selected_exp or is_qpcr or is_hplc

    num_targets = st.sidebar.number_input('ターゲットの数 (1つのグラフにまとめる数):', min_value=1, max_value=10, value=1, step=1) if is_multi_capable else 1

    if 'WB' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: HO-1', 'Loading Control:', '例: HSP90', 'Relative Band Intensity'
    elif 'HPLC' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = '物質名:', '例: PpIX', 'タンパク質濃度:', '例: protein', 'Intracellular Concentration\n[nmol / mg ・ protein]'
    elif 'qPCR' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: PDK1', 'Loading Control:', '例: β-ACTIN', 'Relative mRNA level'
    elif is_mtt:
        t_label, t_ph, l_label, l_ph, y_label_def = '細胞株:', '例: PC3', '薬剤名:', '例: ALA', 'Cell Viability [%]'
    elif is_microscope:
        t_label, t_ph, l_label, l_ph, y_label_def = '観察対象:', '例: ROS / GFP', '', '', 'Relative Fluorescence Intensity'

    is_common_loading = True
    target_names, loading_names = [], []

    if num_targets == 1:
        c_side1, c_side2 = st.sidebar.columns(2)
        with c_side1: t_name_raw = st.text_input(t_label, placeholder=t_ph).strip()
        with c_side2: l_name_raw = st.text_input(l_label, placeholder=l_ph).strip() if not is_microscope else ""
        target_names.append(t_name_raw or ("Cell Line" if is_mtt else "Target"))
        loading_names.append(l_name_raw or ("Drug" if is_mtt else ("" if is_microscope else "Loading Control")))
    else:
        if not is_mtt and not is_microscope:
            is_common_loading = "共通" in st.sidebar.radio("Loading Controlの扱い:", ["共通 (全てのターゲットで同じデータを使用)", "ターゲットごとに個別"])
            if is_common_loading:
                l_name_raw = st.sidebar.text_input(f'共通の {l_label}', placeholder=l_ph).strip()
                loading_names = [l_name_raw or "Loading Control"] * num_targets
            
        st.sidebar.markdown("**ターゲット設定**")
        for i in range(num_targets):
            target_names.append(st.sidebar.text_input(f'{t_label} {i+1}:', placeholder=f'Target {i+1}').strip() or f"Target {i+1}")
            if not is_common_loading and not is_mtt and not is_microscope:
                loading_names.append(st.sidebar.text_input(f'{l_label} {i+1}:', placeholder=f'Loading {i+1}').strip() or f"Loading {i+1}")
                st.sidebar.markdown("---")

    t_name = target_names[0]
    l_name = loading_names[0] if loading_names else ("Drug" if is_mtt else "" if is_microscope else "Loading Control")
    y_label_full = y_label_def if (is_mtt or is_microscope or is_hplc or num_targets > 1) else f"{y_label_def}\n[{t_name} / {l_name}]"
    ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・統計設定")

    error_bar_type = st.sidebar.radio("エラーバーの種類:", ["SD (標準偏差)", "SEM (標準誤差)"])

    if not is_mtt:
        layout_mode = "条件ごとにグループ化" if num_targets > 1 else st.sidebar.radio("棒の配置:", ["均等に並べる", "条件ごとにグループ化"])
        if num_targets > 1: st.sidebar.info("💡 複数ターゲットモードでは、棒の配置は自動的に「ターゲット毎のグループ化」になります。")
            
        color_mode = st.sidebar.radio("配色:", ["すべて黒", "上段ラベルで色分け（黒/グレー）"])
        bar_width_input = st.sidebar.slider("棒の太さ調整:", min_value=0.05, max_value=0.80, value=(0.25 if layout_mode == "条件ごとにグループ化" else 0.17), step=0.01)
        
        pairing_options = ['独立 (パラメトリック)', '独立 (ノンパラメトリック)'] if is_microscope else ['独立 (パラメトリック)', '独立 (ノンパラメトリック)', '対応あり (パラメトリック)', '対応あり (ノンパラメトリック)']
        pairing_mode = st.sidebar.radio('統計検定の前提:', pairing_options)
        
        var_equal = '等しい' in st.sidebar.radio('ばらつき(分散)の仮定:', ['分散が等しいと仮定する (古典的)', '分散が異なると仮定する (Welch等)']) if ('パラメトリック' in pairing_mode and '独立' in pairing_mode) else False
            
        is_vs_control = 'Control' in st.sidebar.radio('比較方式 (3条件以上の場合):', ['すべての組み合わせを総当たりで比較', '一番左の群(Control)とだけ比較'])
        is_non_param = 'ノンパラメトリック' in pairing_mode
        is_paired = '対応あり' in pairing_mode
        norm_mode = st.sidebar.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'])
        is_grouped_test = ('グループ内' in st.sidebar.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'])) if num_targets == 1 else True
    else:
        layout_mode, color_mode, norm_mode = "", "", ""
        bar_width_input = 0.17
        pairing_mode = st.sidebar.radio('統計検定の前提:', ['独立 (パラメトリック)', '独立 (ノンパラメトリック)', '対応あり (パラメトリック)', '対応あり (ノンパラメトリック)'])
        var_equal = '等しい' in st.sidebar.radio('ばらつき(分散)の仮定:', ['分散が等しいと仮定する (古典的)', '分散が異なると仮定する (Welch等)']) if ('パラメトリック' in pairing_mode and '独立' in pairing_mode) else False
        is_vs_control = 'Control' in st.sidebar.radio('比較方式 (3条件以上の場合):', ['すべての組み合わせを総当たりで比較', '一番左の群(Control)とだけ比較'])
        is_non_param = 'ノンパラメトリック' in pairing_mode
        is_paired = '対応あり' in pairing_mode
        is_grouped_test = False

    u_label_name = "系列名" if (not is_mtt and layout_mode == "条件ごとにグループ化" and "色分け" in color_mode) else ("横ラベル上段" if not is_mtt else "")
    d_label_name = "横ラベル" if (not is_mtt and layout_mode == "条件ごとにグループ化" and "色分け" in color_mode) else ("横ラベル下段" if not is_mtt else "")
    paste_t_label = 'Target' if 'WB' in selected_exp or 'qPCR' in selected_exp else ('物質名' if 'HPLC' in selected_exp else t_name)
    paste_l_label = 'Loading Control' if 'WB' in selected_exp or 'qPCR' in selected_exp else ('タンパク質濃度' if 'HPLC' in selected_exp else l_name)

    st.markdown("---")
    
    config = {
        'is_mtt': is_mtt, 'is_microscope': is_microscope, 'is_qpcr': is_qpcr, 'is_hplc': is_hplc,
        'num_targets': num_targets, 'target_names': target_names, 'loading_names': loading_names,
        't_name': t_name, 'l_name': l_name, 'ylabel_input': ylabel_input,
        'error_bar_type': error_bar_type, 'layout_mode': layout_mode, 'color_mode': color_mode,
        'bar_width': bar_width_input, 'var_equal': var_equal, 'is_vs_control': is_vs_control,
        'is_non_param': is_non_param, 'is_paired': is_paired, 'norm_mode': norm_mode,
        'is_grouped_test': is_grouped_test, 'u_label_name': u_label_name, 'd_label_name': d_label_name,
        'paste_t_label': paste_t_label, 'paste_l_label': paste_l_label
    }

    # --- UI 入力画面 ---
    col_input, col_graph = st.columns([1.2, 1.0], gap="large")
    input_data = []

    with col_input:
        st.header("📝 データ入力")
        if is_mtt:
            c1, c2, c3 = st.columns(3)
            config['mtt_ignore_row'] = c1.text_input('空のWell(除外行):', 'A, H')
            config['mtt_ignore_col'] = c2.text_input('空のWell(除外列):', '1')
            config['mtt_blank_col'] = c3.text_input('バックグラウンド（培地のみ）(列):', '12')
            c4, c5 = st.columns(2)
            config['mtt_control_col'] = c4.text_input('Control（細胞生存率100%の基準）(列):', '11')
            config['mtt_sample_cols'] = c5.text_input('Sample(列):', '2-10')
            c6, c7, c8 = st.columns(3)
            config['mtt_start_conc'] = c6.number_input('開始濃度:', value=4000.0)
            config['mtt_dilution'] = c7.number_input('希釈倍率(n倍):', value=2.0)
            config['mtt_unit'] = c8.text_input('単位:', 'μM')
            config['mtt_conc_direction'] = st.radio("濃度の配置方向:", ["左が高濃度 (右へ希釈)", "右が高濃度 (左へ希釈)"], horizontal=True)
            config['mtt_custom_xticks'] = st.text_input('横軸の目盛りに明示したい数値（カンマ区切りで追加指定、空欄なら自動）', value='', placeholder='例: 10, 50, 250')
            
            for i in range(num_cond):
                p_name = st.text_input(f'プレート {i+1} 条件名:', placeholder=f'例: プレート{i+1}', key=f"pname_{i}")
                p_data = st.text_area(f'プレート {i+1} データ (8行x12列):', placeholder='ここにペースト', height=220, key=f"pdata_{i}")
                input_data.append((p_name, p_data))
        else:
            input_mode = "手動で1条件ずつ入力" if is_microscope else st.radio("入力モード:", ["エクセル列ごとに一括ペースト（おすすめ✨）", "手動で1条件ずつ入力"], horizontal=True)
            
            if input_mode == "エクセル列ごとに一括ペースト（おすすめ✨）":
                st.info("💡 エクセル上で離れた列にあってもOK！必要な列だけを個別にコピーしてペーストしてください。\nペースト後に出現する表で、離れたサンプルを隣同士に整理できます。")
                
                bulk_n, bulk_t_list, bulk_l_list = "", [], []
                if num_targets == 1:
                    c_n, c_l, c_t = st.columns(3)
                    bulk_n = c_n.text_area("1. 【名前】の列をペースト", height=150, placeholder="例:\nsiNC\nsiHSPA9")
                    bulk_l_list = [c_l.text_area(f"2. 【{paste_l_label}】", height=150)]
                    bulk_t_list = [c_t.text_area(f"3. 【{paste_t_label}】", height=150)]
                else:
                    if is_common_loading:
                        cols_bulk = st.columns(num_targets + 2)
                        bulk_n = cols_bulk[0].text_area("1. 【名前】", height=150)
                        bulk_l_list = [cols_bulk[1].text_area(f"2. 共通【{paste_l_label}】", height=150)] * num_targets
                        for j in range(num_targets): bulk_t_list.append(cols_bulk[j+2].text_area(f"{j+3}. 【{target_names[j]}】", height=150))
                    else:
                        bulk_n = st.columns([1, 3])[0].text_area("1. 【名前】列", height=150)
                        for j in range(num_targets):
                            ct, cl = st.columns(2)
                            bulk_t_list.append(ct.text_area(f"【{target_names[j]}】", height=150, key=f"bulk_t_{j}"))
                            bulk_l_list.append(cl.text_area(f"対応する【{loading_names[j]}】", height=150, key=f"bulk_l_{j}"))
                
                if bulk_n.strip():
                    try:
                        n_lines = [line.strip() for line in bulk_n.replace('\r', '').split('\n') if line.strip()]
                        t_lines_list = [[line.strip() for line in b.replace('\r', '').split('\n') if line.strip()] if b.strip() else [] for b in bulk_t_list]
                        l_lines_list = [[line.strip() for line in b.replace('\r', '').split('\n') if line.strip()] if b.strip() else [] for b in bulk_l_list]

                        raw_dict = {}
                        for i, name in enumerate(n_lines):
                            if not name: continue
                            if name not in raw_dict: raw_dict[name] = {'t': [[] for _ in range(num_targets)], 'l': [[] for _ in range(num_targets)]}
                            for j in range(num_targets):
                                if i < len(t_lines_list[j]): raw_dict[name]['t'][j].extend([float(x) for x in re.sub(r'[\s,]+', ',', t_lines_list[j][i]).split(',') if x.strip()])
                                if i < len(l_lines_list[j]): raw_dict[name]['l'][j].extend([float(x) for x in re.sub(r'[\s,]+', ',', l_lines_list[j][i]).split(',') if x.strip()])

                        mapping_df = pd.DataFrame({"表示順 (1,2,3...)": range(1, len(raw_dict) + 1), "エクセルの名前 (読取専用)": list(raw_dict.keys()), u_label_name: list(raw_dict.keys()), f"{d_label_name} (空欄可)": [""] * len(raw_dict)})
                        edited_df = st.data_editor(mapping_df, hide_index=True, use_container_width=True, disabled=["エクセルの名前 (読取専用)"]).sort_values(by="表示順 (1,2,3...)")
                        
                        for _, row in edited_df.iterrows():
                            orig_name = row["エクセルの名前 (読取専用)"]
                            u_label = str(row[u_label_name]).strip() if pd.notna(row[u_label_name]) else ""
                            d_label = str(row[f"{d_label_name} (空欄可)"]).strip() if pd.notna(row[f"{d_label_name} (空欄可)"]) else ""
                            input_data.append((u_label, d_label, ['\n'.join(map(str, raw_dict[orig_name]['t'][j])) for j in range(num_targets)], ['\n'.join(map(str, raw_dict[orig_name]['l'][j])) for j in range(num_targets)]))
                    except Exception: st.error("データの読み取りに失敗しました。数字や文字の形式を確認してください。")
            else:
                for i in range(num_cond):
                    st.markdown(f"**条件 {i+1}**") if num_targets > 1 else None
                    if is_microscope:
                        col_up, col_dn = st.columns(2)
                        n_up = col_up.text_input(f'{u_label_name}:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
                        n_down = col_dn.text_input(f'{d_label_name}:', placeholder='(空欄可)', key=f"dn_{i}")
                        
                        n_t_list = []
                        cols_manual = st.columns(num_targets)
                        for j in range(num_targets):
                            with cols_manual[j]:
                                st.markdown(f"**📷 {target_names[j]} 画像解析**")
                                ai_mode = st.radio("モード:", ["標準 (クラウド高速)", "AI (Cellpose・ローカル)"], key=f"mode_{i}_{j}", horizontal=True)
                                uploaded_imgs = st.file_uploader("画像を追加 (複数可)", type=['tif', 'png', 'jpg'], accept_multiple_files=True, key=f"imgs_{i}_{j}")
                                
                                if uploaded_imgs and st.button("🚀 解析を実行", key=f"btn_{i}_{j}"):
                                    with st.spinner("画像解析中..."):
                                        from utils import analyze_images
                                        selected_mode = "standard" if "標準" in ai_mode else "ai"
                                        try:
                                            results = analyze_images(uploaded_imgs, mode=selected_mode)
                                            st.session_state[f"t_val_{i}_{j}"] = "\n".join([f"{val:.3f}" for val in results])
                                            st.success(f"{len(results)}個の細胞を抽出しました！")
                                        except Exception as e:
                                            st.error(str(e))
                                
                                default_val = st.session_state.get(f"t_val_{i}_{j}", "")
                                n_t_list.append(st.text_area(f'{target_names[j]}データ:', value=default_val, placeholder='縦にペースト または 画像から自動抽出', height=100, key=f"t_{i}_{j}"))
                        input_data.append((n_up, n_down, n_t_list, []))
                    elif num_targets == 1:
                        col_up, col_dn, col_l, col_t = st.columns([1, 1, 1.5, 1.5])
                        input_data.append((col_up.text_input(f'{u_label_name}:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}"), col_dn.text_input(f'{d_label_name}:', placeholder='(空欄可)', key=f"dn_{i}"), [col_t.text_area(f'{paste_t_label}:', placeholder='縦にペースト', height=100, key=f"t_{i}")], [col_l.text_area(f'{paste_l_label}:', placeholder='縦にペースト', height=100, key=f"l_{i}")]))
                    else:
                        col_up, col_dn = st.columns(2)
                        n_up = col_up.text_input(f'{u_label_name}:', placeholder='Control' if i==0 else f'Cond_{i+1}', key=f"up_{i}")
                        n_down = col_dn.text_input(f'{d_label_name}:', placeholder='(空欄可)', key=f"dn_{i}")
                        if is_common_loading:
                            cols_manual = st.columns([1.5] + [1.5]*num_targets)
                            n_l_list = [cols_manual[0].text_area(f'共通の {paste_l_label}:', placeholder='縦にペースト', height=100, key=f"l_{i}")] * num_targets
                            input_data.append((n_up, n_down, [cols_manual[1+j].text_area(f'{target_names[j]}:', placeholder='縦にペースト', height=100, key=f"t_{i}_{j}") for j in range(num_targets)], n_l_list))
                        else:
                            n_t_list, n_l_list = [], []
                            for j in range(num_targets):
                                ct, cl = st.columns(2)
                                n_t_list.append(ct.text_area(f'{target_names[j]}:', placeholder='縦にペースト', height=100, key=f"t_{i}_{j}"))
                                n_l_list.append(cl.text_area(f'対応する {loading_names[j]}:', placeholder='縦にペースト', height=100, key=f"l_{i}_{j}"))
                            input_data.append((n_up, n_down, n_t_list, n_l_list))

    # --- UI グラフ表示部 ---
    with col_graph:
        st.header("📊 リアルタイムプレビュー")
        st.info("💡 左の枠に文字を打つとグラフの枠が連動し、数値をペーストすると棒が出現します。")
        
        try:
            if config['is_mtt']:
                render_mtt_analysis(input_data, config)
            elif config['num_targets'] == 1:
                render_single_target(input_data, config)
            else:
                render_multi_target(input_data, config)
        except Exception as e:
            st.error(f"グラフ描画中にエラーが発生しました: {e}")
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
