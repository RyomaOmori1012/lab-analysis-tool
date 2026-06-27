import streamlit as st
import pandas as pd
import numpy as np
import re
import json
import outlier_tools

@st.cache_data(show_spinner=False, max_entries=5)
def get_cached_preview(file_bytes, filename, mode, sigma, sens, dist, area, preview_color):
    from utils import generate_preview_image
    if mode == "ai":
        sigma, sens, dist, area = 0, 0, 0, 0
    return generate_preview_image(file_bytes, filename, mode, sigma, sens, dist, area, preview_color)

def render_data_input(config, num_cond):
    is_mtt = config['is_mtt']
    is_microscope = config['is_microscope']
    label_style = config['label_style']
    d_label_name = config['d_label_name']
    u_label_name = config['u_label_name']
    num_targets = config['num_targets']
    show_stats = config['show_stats']
    paste_t_label = config['paste_t_label']
    paste_l_label = config['paste_l_label']
    p_t_fmt = config['p_t_fmt']
    p_l_fmt = config['p_l_fmt']
    is_common_loading = config.get('is_common_loading', True)
    target_names = config['target_names']
    loading_names = config['loading_names']
    sigma_val = config['sigma_val']
    sens_val = config['sens_val']
    dist_val = config['dist_val']
    area_val = config['area_val']
    preview_color = config['preview_color']

    st.markdown("---")
    
    # アップローダーを安全に新品に取り替えるためのID
    if 'uploader_idx' not in st.session_state:
        st.session_state['uploader_idx'] = 0

    if is_microscope:
        c_head1, c_head2, c_head3 = st.columns([1.2, 0.8, 1])
        with c_head1:
            st.header("📝 データ入力")
        with c_head2:
            st.write("")
            if st.button("🗑️ 全データをクリア", type="primary", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        with c_head3:
            st.write("")
            if st.button("🖼️ 画像のみクリア (軽量化)", use_container_width=True, help="解析後にこれを押すと、抽出した数値は残したまま重い画像ファイルだけを削除して動作をサクサクにします。"):
                # 画像アップローダーのIDを進める
                st.session_state['uploader_idx'] += 1
                st.rerun()
    else:
        c_head1, c_head2 = st.columns([1.2, 1])
        with c_head1:
            st.header("📝 データ入力")
        with c_head2:
            st.write("")
            if st.button("🗑️ 入力データをすべてクリア", type="primary", use_container_width=True):
                st.session_state.clear()
                st.rerun()

    input_data = []

    analyze_all = False
    processed_any = False
    if is_microscope:
        st.info("💡 各Wellに画像をアップロードした後、下のボタンを押すと全ての画像が全自動で連続解析され、数値欄に入力されます。")
        analyze_all = st.button("🚀🚀 アップロード済みの【全ての画像】を一括で解析する 🚀🚀", type="primary", use_container_width=True)

    if not is_mtt:
        if label_style == "1段 ＋ 系列名（凡例）":
            st.info(f"💡 **【1段＋系列名】モード:** \n『{d_label_name}』が同じものが1つのグループにまとまり、『{u_label_name}』ごとに色分けされて凡例として右上に表示されます。")
        else:
            st.info(f"💡 **【2段ラベル】モード:** \n『{d_label_name}』が同じものが1つのグループ（下線）にまとまり、その直上にそれぞれの『{u_label_name}』が印字されます。")

    if is_mtt:
        c1, c2, c3 = st.columns(3)
        
        # 1. 金庫が空なら初期値を入れる
        if 'mtt_ignore_row' not in st.session_state: st.session_state['mtt_ignore_row'] = 'A, H'
        if 'mtt_ignore_col' not in st.session_state: st.session_state['mtt_ignore_col'] = '1'
        if 'mtt_blank_col' not in st.session_state: st.session_state['mtt_blank_col'] = '12'
        
        # 2. ウィジェットには初期値(value)を書かない（金庫の値が自動で表示される）
        config['mtt_ignore_row'] = c1.text_input('空のWell(除外行):', key='mtt_ignore_row')
        config['mtt_ignore_col'] = c2.text_input('空のWell(除外列):', key='mtt_ignore_col')
        config['mtt_blank_col'] = c3.text_input('バックグラウンド（培地のみ）(列):', key='mtt_blank_col')
        
        c4, c5 = st.columns(2)
        if 'mtt_control_col' not in st.session_state: st.session_state['mtt_control_col'] = '11'
        if 'mtt_sample_cols' not in st.session_state: st.session_state['mtt_sample_cols'] = '2-10'
        config['mtt_control_col'] = c4.text_input('Control（細胞生存率100%の基準）(列):', key='mtt_control_col')
        config['mtt_sample_cols'] = c5.text_input('Sample(列):', key='mtt_sample_cols')
        
        c6, c7, c8 = st.columns(3)
        if 'mtt_start_conc' not in st.session_state: st.session_state['mtt_start_conc'] = 4000.0
        if 'mtt_dilution' not in st.session_state: st.session_state['mtt_dilution'] = 2.0
        if 'mtt_unit' not in st.session_state: st.session_state['mtt_unit'] = 'μM'
        
        config['mtt_start_conc'] = c6.number_input('開始濃度:', key='mtt_start_conc')
        config['mtt_dilution'] = c7.number_input('希釈倍率(n倍):', key='mtt_dilution')
        config['mtt_unit'] = c8.text_input('単位:', key='mtt_unit').replace('μ', 'µ')
        config['mtt_conc_direction'] = st.radio("濃度の配置方向:", ["左が高濃度 (右へ希釈)", "右が高濃度 (左へ希釈)"], horizontal=True, key='mtt_conc_direction')
        config['mtt_custom_xticks'] = st.text_input('横軸の目盛りに明示したい数値（カンマ区切りで追加指定、空欄なら自動）', value='', placeholder='例: 10, 50, 250', key='mtt_custom_xticks')
        
        from utils import parse_idx
        i_rows = parse_idx(config['mtt_ignore_row'], True)
        i_cols = parse_idx(config['mtt_ignore_col'], False)
        b_cols = parse_idx(config['mtt_blank_col'], False)
        c_cols = parse_idx(config['mtt_control_col'], False)
        m_cols = parse_idx(config['mtt_mock_col'], False)
        s_cols = parse_idx(config['mtt_sample_cols'], False)
        valid_rows = [r for r in range(8) if r not in i_rows]
        
        if 'mtt_exclude_map' not in config:
            config['mtt_exclude_map'] = {}
            
        for i in range(num_cond):
            with st.container(border=True):
                st.markdown(f"**【 プレート {i+1} 】**")
                if f"pname_{i}" not in st.session_state: st.session_state[f"pname_{i}"] = ""
                p_name = st.text_input(f'条件名:', key=f"pname_{i}")
                exclude_flag = st.checkbox("このプレートを統計検定から除外する", key=f"ex_{i}") if show_stats else False

                mock_lbl_val, cond_lbl_val = "Mock", p_name if p_name else f"Plate {i+1}"
                if config.get('show_mtt_bar', False):
                    st.markdown("<span style='font-size:0.8em; color:gray;'>👇 ベースライン毒性棒グラフの横ラベル設定</span>", unsafe_allow_html=True)
                    c_lbl1, c_lbl2 = st.columns(2)
                    with c_lbl1:
                        if f"mtt_bar_mock_lbl_{i}" not in st.session_state: st.session_state[f"mtt_bar_mock_lbl_{i}"] = "Mock"
                        mock_lbl_val = st.text_input(f"無処理群のラベル:", key=f"mtt_bar_mock_lbl_{i}")
                    with c_lbl2:
                        default_cond_lbl = p_name if p_name.strip() else f"Plate {i+1}"
                        if f"mtt_bar_cond_lbl_{i}" not in st.session_state: 
                            st.session_state[f"mtt_bar_cond_lbl_{i}"] = default_cond_lbl
                        elif st.session_state.get(f"prev_pname_{i}") != p_name:
                            st.session_state[f"mtt_bar_cond_lbl_{i}"] = default_cond_lbl
                        st.session_state[f"prev_pname_{i}"] = p_name
                        cond_lbl_val = st.text_input(f"処理群のラベル:", key=f"mtt_bar_cond_lbl_{i}")
                
                if f"pdata_{i}" not in st.session_state: st.session_state[f"pdata_{i}"] = ""
                p_data = st.text_area(f'データ (8行x12列):', key=f"pdata_{i}", placeholder="エクセルから8行×12列の数値データをそのままコピーしてペーストしてください")
                
                config['mtt_exclude_map'][i] = outlier_tools.render_outlier_ui(
                    p_data, i, config, valid_rows, i_cols, b_cols, c_cols, m_cols, s_cols
                )
                
                input_data.append((p_name, p_data, exclude_flag, mock_lbl_val, cond_lbl_val))

    else:
        input_mode = "手作業モード" if is_microscope else st.radio("入力モード:", ["エクセル列ごとに一括ペースト（おすすめ✨）", "手動で1条件ずつ入力"], horizontal=True, key='input_mode_radio')
        
        if "prev_input_mode" not in st.session_state:
            st.session_state["prev_input_mode"] = input_mode

        if st.session_state["prev_input_mode"] != input_mode:
            st.session_state["prev_input_mode"] = input_mode
            
            for i in range(20):
                orig = f"Cond_{i+1}"
                st.session_state[f"up_{i}"] = st.session_state.data_dict.get(f"u_{orig}", "")
                st.session_state[f"dn_{i}"] = st.session_state.data_dict.get(f"d_{orig}", "")
                st.session_state[f"t_{i}"] = st.session_state.data_dict.get(f"raw_t_{orig}_0", "")
                st.session_state[f"l_{i}"] = st.session_state.data_dict.get(f"raw_l_{orig}_0", "")
                for j in range(10): 
                    st.session_state[f"t_{i}_{j}"] = st.session_state.data_dict.get(f"raw_t_{orig}_{j}", "")
                    st.session_state[f"l_{i}_{j}"] = st.session_state.data_dict.get(f"raw_l_{orig}_{j}", "")
            
            keys_to_delete = [k for k in st.session_state.keys() if k.startswith("editor_df_targets")]
            for k in keys_to_delete:
                del st.session_state[k]

        if input_mode == "エクセル列ごとに一括ペースト（おすすめ✨）":
            c_n_input, c_info = st.columns([1, 2.5])
            n_per_group = c_n_input.number_input("📊 1群あたりのデータ数 (n数):", min_value=1, max_value=100, value=3, step=1, key='n_per_group')
            c_info.info("💡 生データをそのままペーストしてください。指定したn数ごとに自動でグループ化されます。")

            bulk_t_list, bulk_l_list = [], []
            if num_targets == 1:
                if not is_microscope:
                    c_l, c_t = st.columns(2)
                    with c_l:
                        st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>【{paste_l_label}】の列</span>", unsafe_allow_html=True)
                        if "ta_bulk_l_1" not in st.session_state: st.session_state["ta_bulk_l_1"] = ""
                        bulk_l_list = [st.text_area("l_col", height=150, key="ta_bulk_l_1", label_visibility="collapsed", placeholder=p_l_fmt.format(loading=paste_l_label))]
                    with c_t:
                        st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>【{paste_t_label}】の列</span>", unsafe_allow_html=True)
                        if "ta_bulk_t_1" not in st.session_state: st.session_state["ta_bulk_t_1"] = ""
                        bulk_t_list = [st.text_area("t_col", height=150, key="ta_bulk_t_1", label_visibility="collapsed", placeholder=p_t_fmt.format(target=paste_t_label))]
                else:
                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>【{paste_t_label}】の列</span>", unsafe_allow_html=True)
                    if "ta_bulk_t_1" not in st.session_state: st.session_state["ta_bulk_t_1"] = ""
                    bulk_t_list = [st.text_area("t_col", height=150, key="ta_bulk_t_1", label_visibility="collapsed", placeholder=p_t_fmt.format(target=paste_t_label))]
            else:
                if is_common_loading:
                    cols_bulk = st.columns(num_targets + 1)
                    with cols_bulk[0]:
                        st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>共通【{paste_l_label}】</span>", unsafe_allow_html=True)
                        if "ta_bulk_l_com" not in st.session_state: st.session_state["ta_bulk_l_com"] = ""
                        bulk_l_list = [st.text_area("l_com", height=150, key="ta_bulk_l_com", label_visibility="collapsed", placeholder=p_l_fmt.format(loading="共通 "+paste_l_label))] * num_targets
                    for j in range(num_targets):
                        with cols_bulk[j+1]:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>【{target_names[j]}】</span>", unsafe_allow_html=True)
                            if f"ta_bulk_t_com_{j}" not in st.session_state: st.session_state[f"ta_bulk_t_com_{j}"] = ""
                            bulk_t_list.append(st.text_area("t_com", height=150, key=f"ta_bulk_t_com_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=target_names[j])))
                else:
                    for j in range(num_targets):
                        ct, cl = st.columns(2)
                        with ct:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>【{target_names[j]}】</span>", unsafe_allow_html=True)
                            if f"ta_bulk_t_sep_{j}" not in st.session_state: st.session_state[f"ta_bulk_t_sep_{j}"] = ""
                            bulk_t_list.append(st.text_area("t_sep", height=150, key=f"ta_bulk_t_sep_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=target_names[j])))
                        with cl:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>対応する【{loading_names[j]}】</span>", unsafe_allow_html=True)
                            if f"ta_bulk_l_sep_{j}" not in st.session_state: st.session_state[f"ta_bulk_l_sep_{j}"] = ""
                            bulk_l_list.append(st.text_area("l_sep", height=150, key=f"ta_bulk_l_sep_{j}", label_visibility="collapsed", placeholder=p_l_fmt.format(loading=loading_names[j])))
            
            if bulk_t_list and bulk_t_list[0].strip():
                try:
                    flat_t_lists = []
                    for b in bulk_t_list:
                        flat_list = []
                        if b.strip():
                            for line in b.replace('\r', '').split('\n'):
                                if line.strip(): flat_list.extend([float(x) for x in re.sub(r'[\s,]+', ',', line.strip()).split(',') if x.strip()])
                        flat_t_lists.append(flat_list)

                    flat_l_lists = []
                    for b in bulk_l_list:
                        flat_list = []
                        if b.strip():
                            for line in b.replace('\r', '').split('\n'):
                                if line.strip(): flat_list.extend([float(x) for x in re.sub(r'[\s,]+', ',', line.strip()).split(',') if x.strip()])
                        flat_l_lists.append(flat_list)

                    num_raw_items = len(flat_t_lists[0]) if flat_t_lists else 0
                    num_groups = int(np.ceil(num_raw_items / n_per_group))

                    raw_dict = {}
                    for g in range(num_groups):
                        orig = f"Cond_{g+1}"
                        raw_dict[orig] = {'t': [[] for _ in range(num_targets)], 'l': [[] for _ in range(num_targets)]}
                        start_idx = g * n_per_group
                        end_idx = start_idx + n_per_group
                        for j in range(num_targets):
                            if j < len(flat_t_lists): raw_dict[orig]['t'][j].extend(flat_t_lists[j][start_idx:end_idx])
                            if j < len(flat_l_lists) and flat_l_lists[j]: raw_dict[orig]['l'][j].extend(flat_l_lists[j][start_idx:end_idx])
                            
                            st.session_state.data_dict[f"raw_t_{orig}_{j}"] = '\n'.join(map(str, raw_dict[orig]['t'][j]))
                            st.session_state.data_dict[f"raw_l_{orig}_{j}"] = '\n'.join(map(str, raw_dict[orig]['l'][j]))

                    current_style = st.session_state.get("prev_label_style", label_style)
                    df_key = f"editor_df_targets{num_targets}_n{n_per_group}"
                    
                    if df_key not in st.session_state or len(st.session_state[df_key]) != num_groups or current_style != label_style:
                        mapping_data = []
                        for g in range(num_groups):
                            orig = f"Cond_{g+1}"
                            u_val = st.session_state.data_dict.get(f"u_{orig}", "") 
                            d_val = st.session_state.data_dict.get(f"d_{orig}", "")
                            ex_val = st.session_state.data_dict.get(f"ex_{orig}", False)
                            mapping_data.append({"orig_name": orig, "u_label": u_val, "d_label": d_val, "exclude": ex_val})
                        
                        st.session_state[df_key] = pd.DataFrame(mapping_data)
                        st.session_state["prev_label_style"] = label_style
                        
                    edited_df = st.data_editor(
                        st.session_state[df_key], 
                        hide_index=True, 
                        use_container_width=True, 
                        key=f"bulk_editor_widget_{num_targets}_{n_per_group}", 
                        column_config={
                            "orig_name": None,
                            "u_label": st.column_config.TextColumn(u_label_name),
                            "d_label": st.column_config.TextColumn(f"{d_label_name} (空欄可)"),
                            "exclude": st.column_config.CheckboxColumn("検定から除外")
                        }
                    )
                    
                    for _, row in edited_df.iterrows():
                        orig = row["orig_name"]
                        st.session_state.data_dict[f"u_{orig}"] = str(row["u_label"]).strip() if pd.notna(row["u_label"]) else ""
                        st.session_state.data_dict[f"d_{orig}"] = str(row["d_label"]).strip() if pd.notna(row["d_label"]) else ""
                        if show_stats: st.session_state.data_dict[f"ex_{orig}"] = bool(row["exclude"])
                            
                        input_data.append((st.session_state.data_dict[f"u_{orig}"], st.session_state.data_dict[f"d_{orig}"], ['\n'.join(map(str, raw_dict[orig]['t'][j])) for j in range(num_targets)], ['\n'.join(map(str, raw_dict[orig]['l'][j])) for j in range(num_targets)], st.session_state.data_dict.get(f"ex_{orig}", False)))
                except Exception as e: st.error(f"データの読み取りに失敗しました。詳細: {e}")
        else:
            for i in range(num_cond):
                with st.container(border=True):
                    st.markdown(f"**【 条件 {i+1} 】**")
                    col_up, col_dn = st.columns(2)

                    if f"up_{i}" not in st.session_state:
                        st.session_state[f"up_{i}"] = st.session_state.data_dict.get(f"u_Cond_{i+1}", "")
                    if f"dn_{i}" not in st.session_state:
                        st.session_state[f"dn_{i}"] = st.session_state.data_dict.get(f"d_Cond_{i+1}", "")

                    with col_up:
                        st.markdown(f"<span style='font-size:0.9em;font-weight:bold;'>{u_label_name}:</span>", unsafe_allow_html=True)
                        st.text_input("u_hid", key=f"up_{i}", placeholder="(空欄可)", label_visibility="collapsed")

                    with col_dn:
                        st.markdown(f"<span style='font-size:0.9em;font-weight:bold;'>{d_label_name}:</span>", unsafe_allow_html=True)
                        st.text_input("d_hid", key=f"dn_{i}", placeholder="(空欄可)", label_visibility="collapsed")
                        
                    st.session_state.data_dict[f"u_Cond_{i+1}"] = st.session_state[f"up_{i}"]
                    st.session_state.data_dict[f"d_Cond_{i+1}"] = st.session_state[f"dn_{i}"]

                    exclude_flag = st.checkbox("この条件を統計検定から除外する", key=f"ex_{i}") if show_stats else False

                    if is_microscope:
                        num_wells = st.number_input(f"📊 この条件の Well数 (n数):", min_value=1, max_value=20, value=3, step=1, key=f"n_wells_{i}")
                        n_t_list = [] 
                        
                        for j in range(num_targets):
                            tgt_display = target_names[j] if target_names[j] else f"Target {j+1}"
                            st.markdown(f"**📷 {tgt_display} データ入力 / 解析**")
                            c_mode, _ = st.columns([1, 2])
                            ai_mode = c_mode.radio("モード:", ["標準 (クラウド高速)", "AI (Cellpose・ローカル)"], key=f"mode_{i}_{j}", horizontal=True)
                            
                            target_well_data = [] 
                            
                            for w in range(num_wells):
                                with st.expander(f"📥 Well {w+1} データ枠", expanded=True):
                                    
                                    # ★ 消去バグを防ぐための絶対的な金庫キー
                                    dict_key = f"raw_micro_Cond_{i+1}_{j}_{w}"
                                    ta_key = f"ta_widget_{i}_{j}_{w}"

                                    # 1. ページ読み込み時（または画像クリアでウィジェットが消し飛んだ時）、金庫から復元
                                    if ta_key not in st.session_state:
                                        st.session_state[ta_key] = st.session_state.data_dict.get(dict_key, "")

                                    up_idx = st.session_state.get('uploader_idx', 0)
                                    uploaded_imgs = st.file_uploader(f"Well {w+1} の画像を解析して自動入力 (オプション)", type=['tif', 'png', 'jpg', 'czi'], accept_multiple_files=True, key=f"imgs_{i}_{j}_{w}_{up_idx}")
                                    
                                    if uploaded_imgs:
                                        selected_mode = "standard" if "標準" in ai_mode else "ai"
                                        with st.container():
                                            if selected_mode == "standard":
                                                try:
                                                    first_img = uploaded_imgs[0]
                                                    overlay_img, cell_count = get_cached_preview(first_img.getvalue(), first_img.name.lower(), selected_mode, sigma_val, sens_val, dist_val, area_val, preview_color)
                                                    overlay_uint8 = (overlay_img * 255).astype(np.uint8)
                                                    st.image(overlay_uint8, caption=f"プレビュー ({first_img.name}): {cell_count}細胞", width=300)
                                                except Exception as e: st.error(f"プレビューエラー: {e}")
                                            else:
                                                st.info("🧠 AIモード選択中（プレビュー非表示）")

                                    do_analyze = False
                                    if uploaded_imgs:
                                        do_analyze = st.button(f"🚀 Well {w+1} の画像を個別に解析", key=f"btn_{i}_{j}_{w}")

                                    # 2. 解析実行時に、テキストエリアと金庫の「両方」に直接書き込む
                                    if uploaded_imgs and (do_analyze or analyze_all):
                                        with st.spinner(f"条件 {i+1} - Well {w+1} を解析中..."):
                                            from utils import analyze_images
                                            selected_mode = "standard" if "標準" in ai_mode else "ai"
                                            well_cells = []
                                            val_list = []
                                            
                                            for img in uploaded_imgs:
                                                try:
                                                    res, _ = analyze_images([img], mode=selected_mode, sigma=sigma_val, sensitivity=sens_val, min_distance=dist_val, min_area=area_val)
                                                    for val in res:
                                                        well_cells.append({"image": img.name, "val": float(val)})
                                                        val_list.append(str(float(val)))
                                                except Exception as e:
                                                    st.error(f"{img.name} の解析エラー: {e}")
                                            
                                            val_str = "\n".join(val_list)
                                            st.session_state[f"t_json_{i}_{j}_{w}"] = json.dumps(well_cells)
                                            
                                            # ★ ここが命綱：両方に書き込む
                                            st.session_state[ta_key] = val_str
                                            st.session_state.data_dict[dict_key] = val_str
                                            
                                            processed_any = True
                                            if do_analyze:
                                                st.rerun()

                                    stored_json = st.session_state.get(f"t_json_{i}_{j}_{w}", "[]")
                                    try:
                                        cells_data = json.loads(stored_json)
                                    except:
                                        cells_data = []
                                        
                                    cell_count = len(cells_data)
                                    if cell_count > 0:
                                        img_counts = {}
                                        for c in cells_data:
                                            img_name = c.get("image", "Manual Input")
                                            img_counts[img_name] = img_counts.get(img_name, 0) + 1
                                            
                                        detail_str = ", ".join([f"{img}: {cnt}細胞" for img, cnt in img_counts.items()])
                                        st.markdown(f"<span style='color:#4ade80;font-weight:bold;'>✅ 解析完了：合計 {cell_count} 細胞（{detail_str}）</span>", unsafe_allow_html=True)

                                    # 3. テキストエリアの描画
                                    val_text = st.text_area(
                                        "細胞ごとの数値 (別ソフトからのコピペも可能):", 
                                        key=ta_key, 
                                        height=120, 
                                        placeholder="ここにImageJ等で定量した数値を縦にペーストしてください"
                                    )
                                    
                                    # 4. ユーザーが手動で編集・コピペした場合に備え、毎秒金庫にバックアップ
                                    st.session_state.data_dict[dict_key] = val_text
                                    target_well_data.append(val_text)
                            
                            n_t_list.append(target_well_data)
                        
                        input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], n_t_list, [], exclude_flag))
                        
                    elif num_targets == 1:
                        col_t, col_l = st.columns(2)
                        with col_t:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{paste_t_label}:</span>", unsafe_allow_html=True)
                            if f"t_{i}" not in st.session_state: 
                                st.session_state[f"t_{i}"] = st.session_state.data_dict.get(f"raw_t_Cond_{i+1}_0", "")
                            n_t = st.text_area("t_area_1", height=130, key=f"t_{i}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=paste_t_label))
                            st.session_state.data_dict[f"raw_t_Cond_{i+1}_0"] = n_t 
                        with col_l:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{paste_l_label}:</span>", unsafe_allow_html=True)
                            if f"l_{i}" not in st.session_state: 
                                st.session_state[f"l_{i}"] = st.session_state.data_dict.get(f"raw_l_Cond_{i+1}_0", "")
                            n_l = st.text_area("l_area_1", height=130, key=f"l_{i}", label_visibility="collapsed", placeholder=p_l_fmt.format(loading=paste_l_label))
                            st.session_state.data_dict[f"raw_l_Cond_{i+1}_0"] = n_l 
                        input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], [n_t], [n_l], exclude_flag))
                        
                    else:
                        if is_common_loading:
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>共通の {paste_l_label}:</span>", unsafe_allow_html=True)
                            if f"l_{i}" not in st.session_state: 
                                st.session_state[f"l_{i}"] = st.session_state.data_dict.get(f"raw_l_Cond_{i+1}_0", "")
                            n_l_val = st.text_area("l_com_area", height=100, key=f"l_{i}", label_visibility="collapsed", placeholder=p_l_fmt.format(loading="共通の "+paste_l_label))
                            st.session_state.data_dict[f"raw_l_Cond_{i+1}_0"] = n_l_val
                            n_l_list = [n_l_val] * num_targets
                            
                            cols_manual = st.columns(num_targets)
                            n_t_list = []
                            for j in range(num_targets):
                                with cols_manual[j]:
                                    tgt_display = target_names[j] if target_names[j] else f"Target {j+1}"
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{tgt_display}:</span>", unsafe_allow_html=True)
                                    if f"t_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"t_{i}_{j}"] = st.session_state.data_dict.get(f"raw_t_Cond_{i+1}_{j}", "")
                                    n_t_val = st.text_area("t_com_area", height=100, key=f"t_{i}_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=tgt_display))
                                    st.session_state.data_dict[f"raw_t_Cond_{i+1}_{j}"] = n_t_val
                                    n_t_list.append(n_t_val)
                            input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], n_t_list, n_l_list, exclude_flag))
                        else:
                            n_t_list, n_l_list = [], []
                            for j in range(num_targets):
                                ct, cl = st.columns(2)
                                tgt_display = target_names[j] if target_names[j] else f"Target {j+1}"
                                load_display = loading_names[j] if loading_names[j] else f"Loading {j+1}"
                                with ct:
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{tgt_display}:</span>", unsafe_allow_html=True)
                                    if f"t_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"t_{i}_{j}"] = st.session_state.data_dict.get(f"raw_t_Cond_{i+1}_{j}", "")
                                    n_t_val = st.text_area("t_sep_area", height=100, key=f"t_{i}_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=tgt_display))
                                    st.session_state.data_dict[f"raw_t_Cond_{i+1}_{j}"] = n_t_val
                                    n_t_list.append(n_t_val)
                                with cl:
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>対応する {load_display}:</span>", unsafe_allow_html=True)
                                    if f"l_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"l_{i}_{j}"] = st.session_state.data_dict.get(f"raw_l_Cond_{i+1}_{j}", "")
                                    n_l_val = st.text_area("l_sep_area", height=100, key=f"l_{i}_{j}", label_visibility="collapsed", placeholder=p_l_fmt.format(loading=load_display))
                                    st.session_state.data_dict[f"raw_l_Cond_{i+1}_{j}"] = n_l_val
                                    n_l_list.append(n_l_val)
                            input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], n_t_list, n_l_list, exclude_flag))

    if is_microscope and analyze_all and processed_any:
        st.toast("✨ すべての画像の解析と数値の抽出が完了しました！")
        st.rerun()

    return input_data