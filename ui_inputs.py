import streamlit as st
import pandas as pd
import numpy as np
import re

@st.cache_data(show_spinner=False, max_entries=5)
def get_cached_preview(file_bytes, filename, mode, sigma, sens, dist, area, preview_color):
    from utils import generate_preview_image
    if mode == "ai":
        sigma, sens, dist, area = 0, 0, 0, 0
    return generate_preview_image(file_bytes, filename, mode, sigma, sens, dist, area, preview_color)

def render_data_input(config, num_cond):
    st.markdown("---")
    c_head1, c_head2 = st.columns([1.2, 1])
    with c_head1:
        st.header("📝 データ入力")
    with c_head2:
        st.write("")
        if st.button("🗑️ 入力データをすべてクリア", type="primary", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    input_data = []

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

    if not is_mtt:
        if label_style == "1段 ＋ 系列名（凡例）":
            st.info(f"💡 **【1段＋系列名】モード:** \n『{d_label_name}』が同じものが1つのグループにまとまり、『{u_label_name}』ごとに色分けされて凡例として右上に表示されます。")
        else:
            st.info(f"💡 **【2段ラベル】モード:** \n『{d_label_name}』が同じものが1つのグループ（下線）にまとまり、その直上にそれぞれの『{u_label_name}』が印字されます。")

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
            with st.container(border=True):
                st.markdown(f"**【 プレート {i+1} 】**")
                if f"pname_{i}" not in st.session_state: st.session_state[f"pname_{i}"] = ""
                p_name = st.text_input(f'条件名:', key=f"pname_{i}")
                exclude_flag = st.checkbox("このプレートを統計検定から除外する", key=f"ex_{i}") if show_stats else False
                if f"pdata_{i}" not in st.session_state: st.session_state[f"pdata_{i}"] = ""
                p_data = st.text_area(f'データ (8行x12列):', key=f"pdata_{i}", placeholder="エクセルから8行×12列の数値データをそのままコピーしてペーストしてください\n\n(例)\n0.123\t0.125\t0.130\t...\n0.110\t0.115\t0.120\t...\n...")
                input_data.append((p_name, p_data, exclude_flag))
    else:
        input_mode = "手動で1条件ずつ入力" if is_microscope else st.radio("入力モード:", ["エクセル列ごとに一括ペースト（おすすめ✨）", "手動で1条件ずつ入力"], horizontal=True)
        
        if "prev_input_mode" not in st.session_state:
            st.session_state["prev_input_mode"] = input_mode

        if st.session_state["prev_input_mode"] != input_mode:
            st.session_state["prev_input_mode"] = input_mode
            
            for i in range(20):
                orig = f"Cond_{i+1}"
                st.session_state[f"up_{i}"] = st.session_state.data_dict.get(f"u_{orig}", "Control" if i == 0 else orig)
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
            n_per_group = c_n_input.number_input("📊 1群あたりのデータ数 (n数):", min_value=1, max_value=100, value=3, step=1)
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
                            u_val = st.session_state.data_dict.get(f"u_{orig}", orig)
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
                        st.session_state[f"up_{i}"] = st.session_state.data_dict.get(f"u_Cond_{i+1}", "Control" if i == 0 else f"Cond_{i+1}")
                    if f"dn_{i}" not in st.session_state:
                        st.session_state[f"dn_{i}"] = st.session_state.data_dict.get(f"d_Cond_{i+1}", "")

                    with col_up:
                        st.markdown(
                            f"<span style='font-size:0.9em;font-weight:bold;'>{u_label_name}:</span>",
                            unsafe_allow_html=True
                        )
                        st.text_input(
                            "u_hid",
                            key=f"up_{i}",
                            label_visibility="collapsed"
                        )

                    with col_dn:
                        st.markdown(
                            f"<span style='font-size:0.9em;font-weight:bold;'>{d_label_name}:</span>",
                            unsafe_allow_html=True
                        )
                        st.text_input(
                            "d_hid",
                            key=f"dn_{i}",
                            placeholder="(空欄可)",
                            label_visibility="collapsed"
                        )
                        
                    st.session_state.data_dict[f"u_Cond_{i+1}"] = st.session_state[f"up_{i}"]
                    st.session_state.data_dict[f"d_Cond_{i+1}"] = st.session_state[f"dn_{i}"]

                    exclude_flag = st.checkbox("この条件を統計検定から除外する", key=f"ex_{i}") if show_stats else False

                    if is_microscope:
                        n_t_list = []
                        for j in range(num_targets):
                            st.markdown(f"**📷 {target_names[j]} 画像解析**")
                            c_mode, c_upload = st.columns([1, 2])
                            ai_mode = c_mode.radio("モード:", ["標準 (クラウド高速)", "AI (Cellpose・ローカル)"], key=f"mode_{i}_{j}", horizontal=True)
                            uploaded_imgs = c_upload.file_uploader("画像を追加 (複数可)", type=['tif', 'png', 'jpg', 'czi'], accept_multiple_files=True, key=f"imgs_{i}_{j}")
                            
                            if uploaded_imgs:
                                selected_mode = "standard" if "標準" in ai_mode else "ai"
                                has_results = st.session_state.get(f"t_{i}_{j}", "") != ""
                                
                                with st.expander("👁️ 抽出プレビュー (1枚目の画像で確認)", expanded=(selected_mode == "standard" or has_results)):
                                    if selected_mode == "standard":
                                        try:
                                            first_img = uploaded_imgs[0]
                                            with st.spinner("画像処理中..."):
                                                overlay_img, cell_count = get_cached_preview(first_img.getvalue(), first_img.name.lower(), selected_mode, sigma_val, sens_val, dist_val, area_val, preview_color)
                                            overlay_uint8 = (overlay_img * 255).astype(np.uint8)
                                            st.image(overlay_uint8, caption=f"1枚目 ({first_img.name}) の検出細胞数: {cell_count}個", use_container_width=True)
                                            
                                            if has_results: st.success(st.session_state.get(f"msg_{i}_{j}", "✨ 解析完了！"))
                                        except Exception as e: st.error(f"プレビューエラー: {e}")
                                    else:
                                        if has_results:
                                            try:
                                                first_img = uploaded_imgs[0]
                                                with st.spinner("結果画像を描画中..."):
                                                    overlay_img, cell_count = get_cached_preview(first_img.getvalue(), first_img.name.lower(), selected_mode, 0, 0, 0, 0, preview_color)
                                                overlay_uint8 = (overlay_img * 255).astype(np.uint8)
                                                st.image(overlay_uint8, caption=f"1枚目 ({first_img.name}) のAI検出細胞: {cell_count}個", use_container_width=True)
                                                st.success(st.session_state.get(f"msg_{i}_{j}", "✨ 解析完了！"))
                                            except Exception as e: st.error(f"結果画像エラー: {e}")
                                        else: st.info("🧠 AIモードが選択されています。事前のプレビューは一時停止しています。")

                            if uploaded_imgs and st.button("🚀 以上の設定で全画像を解析実行", key=f"btn_{i}_{j}", type="primary"):
                                with st.spinner("全画像の解析中..." if ("標準" not in ai_mode) else "全画像の解析中..."):
                                    from utils import analyze_images
                                    selected_mode = "standard" if "標準" in ai_mode else "ai"
                                    try:
                                        results, summary_text = analyze_images(uploaded_imgs, mode=selected_mode, sigma=sigma_val, sensitivity=sens_val, min_distance=dist_val, min_area=area_val)
                                        st.session_state[f"t_{i}_{j}"] = "\n".join([f"{val:.3f}" for val in results])
                                        st.session_state[f"msg_{i}_{j}"] = f"✨ 合計 {len(results)} 個の細胞を抽出しました！\n\n（内訳👉 {summary_text}）"
                                        st.rerun()
                                    except Exception as e: st.error(str(e))
                            
                            st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{target_names[j]}データ:</span>", unsafe_allow_html=True)
                            if f"t_{i}_{j}" not in st.session_state: st.session_state[f"t_{i}_{j}"] = ""
                            n_t_list.append(st.text_area("t_area", height=130, key=f"t_{i}_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=target_names[j])))
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
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{target_names[j]}:</span>", unsafe_allow_html=True)
                                    if f"t_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"t_{i}_{j}"] = st.session_state.data_dict.get(f"raw_t_Cond_{i+1}_{j}", "")
                                    n_t_val = st.text_area("t_com_area", height=100, key=f"t_{i}_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=target_names[j]))
                                    st.session_state.data_dict[f"raw_t_Cond_{i+1}_{j}"] = n_t_val
                                    n_t_list.append(n_t_val)
                            input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], n_t_list, n_l_list, exclude_flag))
                        else:
                            n_t_list, n_l_list = [], []
                            for j in range(num_targets):
                                ct, cl = st.columns(2)
                                with ct:
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>{target_names[j]}:</span>", unsafe_allow_html=True)
                                    if f"t_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"t_{i}_{j}"] = st.session_state.data_dict.get(f"raw_t_Cond_{i+1}_{j}", "")
                                    n_t_val = st.text_area("t_sep_area", height=100, key=f"t_{i}_{j}", label_visibility="collapsed", placeholder=p_t_fmt.format(target=target_names[j]))
                                    st.session_state.data_dict[f"raw_t_Cond_{i+1}_{j}"] = n_t_val
                                    n_t_list.append(n_t_val)
                                with cl:
                                    st.markdown(f"<span style='font-size: 0.9em; font-weight: bold;'>対応する {loading_names[j]}:</span>", unsafe_allow_html=True)
                                    if f"l_{i}_{j}" not in st.session_state: 
                                        st.session_state[f"l_{i}_{j}"] = st.session_state.data_dict.get(f"raw_l_Cond_{i+1}_{j}", "")
                                    n_l_val = st.text_area("l_sep_area", height=100, key=f"l_{i}_{j}", label_visibility="collapsed", placeholder=p_l_fmt.format(loading=loading_names[j]))
                                    st.session_state.data_dict[f"raw_l_Cond_{i+1}_{j}"] = n_l_val
                                    n_l_list.append(n_l_val)
                            input_data.append((st.session_state[f"up_{i}"], st.session_state[f"dn_{i}"], n_t_list, n_l_list, exclude_flag))

    return input_data
