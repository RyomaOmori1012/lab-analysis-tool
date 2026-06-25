import streamlit as st

def init_ss(k, v):
    if k not in st.session_state:
        st.session_state[k] = v

def setup_config(col_input):
    st.sidebar.header("⚙️ 全体設定")
    selected_exp = st.sidebar.selectbox('実験手法:', [
        'Western Blotting (WB)', 
        'HPLC', 
        'qPCR', 
        'MTT Assay (細胞生存率・折れ線比較)', 
        'MTT Assay (IC50・シグモイド曲線)', 
        '蛍光顕微鏡 (Box Plot)'
    ], key='selected_exp')
    
    init_ss('num_cond', 2)
    num_cond = st.sidebar.number_input('手動モード時の条件数:', min_value=1, max_value=20, step=1, key='num_cond')

    is_mtt_ic50 = 'IC50' in selected_exp
    is_mtt_any = 'MTT' in selected_exp
    
    is_microscope = '顕微鏡' in selected_exp
    is_qpcr = 'qPCR' in selected_exp
    is_hplc = 'HPLC' in selected_exp
    is_multi_capable = 'WB' in selected_exp or is_qpcr or is_hplc

    init_ss('num_targets', 1)
    num_targets = st.sidebar.number_input('ターゲットの数 (1つのグラフにまとめる数):', min_value=1, max_value=10, step=1, key='num_targets') if is_multi_capable else 1

    if 'WB' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: HO-1', 'Loading Control:', '例: HSP90', 'Relative Band Intensity'
    elif 'HPLC' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = '物質名:', '例: PpIX', 'タンパク質濃度:', '例: protein', 'Intracellular Concentration\n[nmol / mg ・ protein]'
    elif 'qPCR' in selected_exp:
        t_label, t_ph, l_label, l_ph, y_label_def = 'Target:', '例: PDK1', 'Loading Control:', '例: β-ACTIN', 'Relative mRNA level'
    elif is_mtt_any:
        t_label, t_ph, l_label, l_ph, y_label_def = '細胞株:', '例: PC3', '薬剤名:', '例: ALA', 'Cell Viability [%]'
    elif is_microscope:
        t_label, t_ph, l_label, l_ph, y_label_def = '観察対象:', '例: ROS / GFP', '', '', 'Relative Fluorescence Intensity'

    is_common_loading = True
    target_names, loading_names = [], []

    with col_input:
        st.header("🎯 ターゲット設定")
        if num_targets == 1:
            c_t, c_l = st.columns(2)
            init_ss('t_name_raw_0', '')
            init_ss('l_name_raw_0', '')
            with c_t: t_name_raw = st.text_input(t_label, placeholder=t_ph, key='t_name_raw_0').strip()
            with c_l: l_name_raw = st.text_input(l_label, placeholder=l_ph, key='l_name_raw_0').strip() if not is_microscope else ""
            target_names.append(t_name_raw)
            loading_names.append(l_name_raw)
        else:
            if not is_mtt_any and not is_microscope:
                is_common_loading = "共通" in st.radio("Loading Controlの扱い:", ["共通 (全てのターゲットで同じデータを使用)", "ターゲットごとに個別"], horizontal=True, key='is_common_loading_radio')
                if is_common_loading:
                    init_ss('l_name_raw_com', '')
                    l_name_raw = st.text_input(f'共通の {l_label}', placeholder=l_ph, key='l_name_raw_com').strip()
                    loading_names = [l_name_raw] * num_targets
            
            for i in range(num_targets):
                init_ss(f't_name_raw_{i+1}', '')
                init_ss(f'l_name_raw_{i+1}', '')
                if not is_common_loading and not is_mtt_any and not is_microscope:
                    c_t, c_l = st.columns(2)
                    with c_t: target_names.append(st.text_input(f'{t_label} {i+1}:', placeholder=f'Target {i+1}', key=f't_name_raw_{i+1}').strip())
                    with c_l: loading_names.append(st.text_input(f'{l_label} {i+1}:', placeholder=f'Loading {i+1}', key=f'l_name_raw_{i+1}').strip())
                else:
                    target_names.append(st.text_input(f'{t_label} {i+1}:', placeholder=f'Target {i+1}', key=f't_name_raw_{i+1}').strip())
                    if is_mtt_any: loading_names.append("Drug")
                    elif is_microscope: loading_names.append("")

    t_name = target_names[0] if target_names else ""
    l_name = loading_names[0] if loading_names else ""
    
    # ★ 修正: 入力欄が空欄でも、Y軸ラベルのデフォルト文字には Target 等を補う
    display_t_name = t_name if t_name else "Target"
    display_l_name = l_name if l_name else "Loading Control"

    if is_mtt_any or is_microscope or is_hplc or num_targets > 1:
        y_label_full = y_label_def
    else:
        y_label_full = f"{y_label_def}\n[{display_t_name} / {display_l_name}]"
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 グラフ・軸設定**")
    ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

    microscope_stat = "median"
    if is_microscope:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔬 顕微鏡データ・統計設定")
        init_ss('microscope_stat_ui', '中央値 (Median) - 外れ値に強い・推奨')
        m_stat_choice = st.sidebar.radio(
            "ウェル代表値の算出方法:", 
            ['中央値 (Median) - 外れ値に強い・推奨', '平均値 (Mean) - 全体量を重視'], 
            key='microscope_stat_ui'
        )
        microscope_stat = "median" if "中央値" in m_stat_choice else "mean"

        with st.sidebar.expander("❓ 調整のコツ（何が変わるの？）", expanded=False):
            st.markdown("""
            プレビュー画像の**「黄色の輪郭線」**を見ながら調整してください。
            * **1. ぼかしの強さ (Sigma)**  
              画像のノイズ（ざらつき）を滑らかにします。大きくすると細胞の形が丸くまとまり、小さすぎると1つの細胞が細かく分裂して認識されやすくなります。
            * **2. 閾値の感度 (Sensitivity)**  
              細胞と背景を分ける基準の厳しさです。小さくする（0.8など）と暗い細胞も拾いますがノイズも増えます。大きくする（1.2など）と明るくはっきりした細胞だけを厳選します。
            * **3. 細胞間の最小距離 (ピクセル)**  
              くっついている細胞を「分離」する力です。小さくすると1つの細胞を複数に分割してしまい、大きくしすぎると隣り合う細胞を1つの塊としてカウントしてしまいます。
            * **4. 細胞の最小サイズ (ピクセル)**  
              ゴミ除去フィルターです。ここで指定した面積（ピクセル）よりも小さいオブジェクトは、細胞ではなくゴミ（または死細胞の破片など）とみなして無視します。
            """)
        with st.sidebar.expander("🔬 画像解析パラメータ (標準モード用)", expanded=False):
            preview_color = st.selectbox("🎨 プレビューの表示色:", ["自動 (メタデータから判別)", "緑 (Green)", "赤 (Red)", "青 (Blue)", "シアン (Cyan)", "マゼンタ (Magenta)", "白黒 (Gray)"], key='preview_color')
            init_ss('sigma_val', 1.5)
            sigma_val = st.slider("1. ぼかしの強さ (Sigma):", min_value=0.5, max_value=10.0, step=0.5, key='sigma_val')
            init_ss('sens_val', 1.0)
            sens_val = st.slider("2. 閾値の感度 (Sensitivity):", min_value=0.5, max_value=2.0, step=0.1, key='sens_val')
            init_ss('dist_val', 20)
            dist_val = st.slider("3. 細胞間の最小距離 (ピクセル):", min_value=5, max_value=150, step=5, key='dist_val')
            init_ss('area_val', 200)
            area_val = st.slider("4. 細胞の最小サイズ (ピクセル):", min_value=10, max_value=2000, step=10, key='area_val')
    else:
        preview_color = "自動 (メタデータから判別)"
        sigma_val, sens_val, dist_val, area_val = 1.5, 1.0, 20, 200

    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・統計設定")

    init_ss('show_stats', True)
    show_stats = st.sidebar.toggle("統計結果（★）をグラフに表示する", key='show_stats')
    
    error_bar_type = "SD (標準偏差)"
    var_equal = False
    is_vs_control = False
    is_non_param = False
    is_paired = False
    norm_mode = '全体基準 (一番上の条件で全て規格化)'
    is_grouped_test = True if num_targets > 1 else False

    if show_stats:
        with st.sidebar.expander("📐 統計検定の詳細設定", expanded=False):
            error_bar_type = st.radio("エラーバーの種類:", ["SD (標準偏差)", "SEM (標準誤差)"], key='error_bar_type')
            
            if not is_mtt_any:
                pairing_options = ['独立 (パラメトリック)', '独立 (ノンパラメトリック)'] if is_microscope else ['独立 (パラメトリック)', '独立 (ノンパラメトリック)', '対応あり (パラメトリック)', '対応あり (ノンパラメトリック)']
                pairing_mode = st.radio('統計検定の前提:', pairing_options, key='pairing_mode')
                var_equal = '等しい' in st.radio('ばらつき(分散)の仮定:', ['分散が等しいと仮定する (古典的)', '分散が異なると仮定する (Welch等)'], key='var_equal_radio') if ('パラメトリック' in pairing_mode and '独立' in pairing_mode) else False
                is_vs_control = 'Control' in st.radio('比較方式 (3条件以上の場合):', ['すべての組み合わせを総当たりで比較', '一番左の群(Control)とだけ比較'], key='is_vs_control_radio')
                is_non_param = 'ノンパラメトリック' in pairing_mode
                is_paired = '対応あり' in pairing_mode
                norm_mode = st.radio('規格化:', ['全体基準 (一番上の条件で全て規格化)', 'グループ基準 (下段ラベル毎の先頭条件で規格化)'], key='norm_mode_radio')
                is_grouped_test = ('グループ内' in st.radio('検定範囲:', ['すべての条件間で検定', 'グループ内でのみ検定 (下段ラベルが同じ条件間)'], key='is_grouped_test_radio')) if num_targets == 1 else True
            else:
                pairing_mode = st.radio('統計検定の前提:', ['独立 (パラメトリック)', '独立 (ノンパラメトリック)', '対応あり (パラメトリック)', '対応あり (ノンパラメトリック)'], key='pairing_mode')
                var_equal = '等しい' in st.radio('ばらつき(分散)の仮定:', ['分散が等しいと仮定する (古典的)', '分散が異なると仮定する (Welch等)'], key='var_equal_radio') if ('パラメトリック' in pairing_mode and '独立' in pairing_mode) else False
                is_vs_control = 'Control' in st.radio('比較方式 (3条件以上の場合):', ['すべての組み合わせを総当たりで比較', '一番左の群(Control)とだけ比較'], key='is_vs_control_radio')
                is_non_param = 'ノンパラメトリック' in pairing_mode
                is_paired = '対応あり' in pairing_mode
                is_grouped_test = False

    st.sidebar.markdown("**📏 出力設定**")
    init_ss('svg_font_path', True)
    svg_font_path = st.sidebar.checkbox("SVG文字のアウトライン化 (パワポズレ防止)", key='svg_font_path')

    init_ss('mtt_outlier_mode', '通常 (p < 0.05)')
    if is_mtt_any:
        with st.sidebar.expander("🚨 外れ値検知センサー設定", expanded=True):
            mtt_outlier_mode = st.radio("検知感度 (スミルノフ・グラブス検定):", ['オフ', '通常 (p < 0.05)', '厳しめ (p < 0.01)'], key='mtt_outlier_mode')
    else:
        mtt_outlier_mode = 'オフ'

    mtt_markers, mtt_colors = [], []
    ic50_fix_bottom = False
    ic50_ctrl_gap = 1.0
    
    show_mtt_bar = False
    mtt_mock_col = '12'
    mtt_bar_color = 'グラデーション (黒→灰)'
    mtt_bar_width = 0.4
    mtt_bar_gap = 0.05
    mtt_group_gap = 0.6

    if not is_mtt_any:
        with st.sidebar.expander("📊 グラフの基本レイアウト", expanded=False):
            layout_mode = "条件ごとにグループ化" if num_targets > 1 else st.radio("棒の配置:", ["条件ごとにグループ化", "均等に並べる"], index=1, key='layout_mode_radio')
            label_style = st.radio("X軸ラベルの表示形式:", ["1段 ＋ 系列名（凡例）", "横ラベルを2段にする（上下段）"], index=1, key='label_style_radio')
            color_mode = st.radio("棒の配色:", ["色分け", "すべて黒"], index=1, key='color_mode_radio')
    else:
        layout_mode, norm_mode, label_style = "", "", "横ラベルを2段にする（上下段）"
        color_mode = ""
        
        with st.sidebar.expander("🎨 MTTグラフのデザイン（条件別）", expanded=False):
            st.markdown("条件（プレート）毎のマーカーと色を指定")
            color_options = {
                "🔴 赤 (Red)": "#E41A1C", "🔵 青 (Blue)": "#377EB8", "🟢 緑 (Green)": "#4DAF4A",
                "🟣 紫 (Purple)": "#984EA3", "🟠 オレンジ (Orange)": "#FF7F00", "🟤 茶色 (Brown)": "#A65628",
                "🩷 ピンク (Pink)": "#F781BF", "⚫ 黒 (Black)": "#000000", "🔘 灰色 (Gray)": "#999999"
            }
            marker_options = {
                "● 丸 (Circle)": "o", "▲ 三角 (Triangle)": "^", "■ 四角 (Square)": "s", 
                "◆ ひし形 (Diamond)": "D", "★ 星 (Star)": "*", "✖ バツ (Cross)": "X"
            }
            color_keys = list(color_options.keys())
            marker_keys = list(marker_options.keys())
            
            for i in range(num_cond):
                st.markdown(f"**【 条件 {i+1} 】**")
                c1, c2 = st.columns(2)
                with c1:
                    init_ss(f"mtt_m_{i}", marker_keys[0])
                    sel_m = st.selectbox(f"マーカー {i+1}:", marker_keys, key=f"mtt_m_{i}", label_visibility="collapsed")
                    mtt_markers.append(marker_options[sel_m])
                with c2:
                    init_ss(f"mtt_c_{i}", color_keys[i % len(color_keys)])
                    sel_c = st.selectbox(f"色 {i+1}:", color_keys, key=f"mtt_c_{i}", label_visibility="collapsed")
                    mtt_colors.append(color_options[sel_c])

        if is_mtt_ic50:
            with st.sidebar.expander("📈 IC50曲線の詳細設定", expanded=True):
                init_ss('ic50_fix_bottom', True)
                ic50_fix_bottom = st.checkbox("曲線のBottom(底)を 0% 付近に固定する", key='ic50_fix_bottom', help="最大濃度でも細胞が全滅していない場合、このチェックを入れることでPrismと同じような綺麗なS字を描きやすくなります。")
                
                init_ss('ic50_ctrl_gap', 1.0)
                ic50_ctrl_gap = st.slider("Control(濃度0)と最低濃度の表示間隔 (Log):", min_value=0.5, max_value=2.0, step=0.1, key='ic50_ctrl_gap', help="グラフ左端の「0」と最初のプロットの間隔を調整します。1.0前後が見栄えの黄金比です。")

        with st.sidebar.expander("🌿 ベースライン毒性（Mock比較）設定", expanded=True):
            init_ss('show_mtt_bar', False)
            show_mtt_bar = st.checkbox("ベースライン毒性評価用の棒グラフも同時に作成する", key='show_mtt_bar', help="ALA未添加状態での、完全無処理(Mock)とsiRNA等のトランスフェクション毒性を比較する棒グラフを出力します。")
            if show_mtt_bar:
                init_ss('mtt_mock_col', '12')
                mtt_mock_col = st.text_input("完全無処理(Mock)の列:", value='12', key='mtt_mock_col', help="プレート内で薬物を一切入れず、トランスフェクションもしていない完全コントロールの列番号を指定してください。")
                
                st.markdown("<span style='font-size: 0.9em; font-weight:bold;'>🎨 棒グラフのデザイン設定</span>", unsafe_allow_html=True)
                init_ss('mtt_bar_color', 'グラデーション (黒→灰)')
                mtt_bar_color = st.radio("棒の配色:", ["グラデーション (黒→灰)", "すべて黒"], key='mtt_bar_color')
                
                init_ss('mtt_bar_width', 0.4)
                mtt_bar_width = st.slider("棒の太さ:", min_value=0.1, max_value=1.0, value=0.4, step=0.05, key='mtt_bar_width')
                
                init_ss('mtt_bar_gap', 0.05)
                mtt_bar_gap = st.slider("Mockと処理群の間隔:", min_value=0.0, max_value=1.0, value=0.05, step=0.05, key='mtt_bar_gap')
                
                init_ss('mtt_group_gap', 0.6)
                mtt_group_gap = st.slider("プレート間の間隔:", min_value=0.0, max_value=2.0, value=0.6, step=0.1, key='mtt_group_gap')

    st.sidebar.markdown("---")
    st.sidebar.header("🎨 グラフ詳細デザイン調整")
    with st.sidebar.expander("文字サイズ・グラフ幅・棒の微調整", expanded=False):
        init_ss('fig_width', 0.0)
        fig_width = st.slider("グラフの横幅 (0で自動):", min_value=0.0, max_value=30.0, step=0.5, key='fig_width')
        init_ss('fig_height', 5.0)
        fig_height = st.slider("グラフの縦幅:", min_value=3.0, max_value=20.0, step=0.5, key='fig_height')
        init_ss('title_fontsize', 14)
        title_fontsize = st.slider("タイトルの文字サイズ:", min_value=8, max_value=36, step=1, key='title_fontsize')
        init_ss('label_fontsize', 16)
        label_fontsize = st.slider("軸ラベル(Y軸等)の文字サイズ:", min_value=8, max_value=36, step=1, key='label_fontsize')
        
        if not is_mtt_any:
            init_ss('tick_fontsize', 14)
            tick_fontsize = st.slider("目盛り(数値)の文字サイズ:", min_value=8, max_value=36, step=1, key='tick_fontsize')
            init_ss('x_label_fontsize', 14)
            x_label_fontsize = st.slider("横ラベル(条件名等)の文字サイズ:", min_value=8, max_value=36, step=1, key='x_label_fontsize')
        else:
            init_ss('tick_fontsize', 12)
            tick_fontsize = st.slider("縦横の目盛り(数値)の文字サイズ:", min_value=8, max_value=36, step=1, key='tick_fontsize')
            x_label_fontsize = 14

        init_ss('legend_fontsize', 12)
        legend_fontsize = st.slider("凡例の文字サイズ:", min_value=8, max_value=36, step=1, key='legend_fontsize')
        
        st.markdown("---")
        default_y_tick = 20.0 if is_mtt_any else 0.0
        init_ss('y_tick_interval', default_y_tick)
        y_tick_interval = st.number_input("縦軸(Y軸)の目盛り間隔 (0で自動):", min_value=0.0, max_value=1000000.0, step=0.1, key='y_tick_interval')

        if not is_mtt_any:
            st.markdown("---")
            def_bw = 0.25 if layout_mode == "条件ごとにグループ化" else 0.17
            init_ss('bar_width_input', def_bw)
            bar_width_input = st.slider("棒の太さ調整:", min_value=0.05, max_value=0.80, step=0.01, key='bar_width_input')
            if layout_mode == "条件ごとにグループ化":
                init_ss('bar_gap_input_g', 0.02)
                bar_gap_input = st.slider("グループ内の棒の間隔:", min_value=0.0, max_value=1.50, step=0.01, key='bar_gap_input_g')
                init_ss('group_gap_input_g', 0.50)
                group_gap_input = st.slider("グループ間の間隔:", min_value=0.0, max_value=3.00, step=0.05, key='group_gap_input_g')
            else:
                init_ss('bar_gap_input_s', 0.50)
                bar_gap_input = st.slider("棒の間隔調整:", min_value=0.0, max_value=1.50, step=0.01, key='bar_gap_input_s')
                group_gap_input = 0.0
        else:
            bar_width_input = 0.17
            bar_gap_input = 0.02
            group_gap_input = 0.0

    if label_style == "1段 ＋ 系列名（凡例）":
        u_label_name = "系列名"
        d_label_name = "横ラベル"
    else:
        u_label_name = "横ラベル上段"
        d_label_name = "横ラベル下段"

    paste_t_label = 'Target' if 'WB' in selected_exp or 'qPCR' in selected_exp else ('物質名' if 'HPLC' in selected_exp else t_name)
    paste_l_label = 'Loading Control' if 'WB' in selected_exp or 'qPCR' in selected_exp else ('タンパク質濃度' if 'HPLC' in selected_exp else l_name)

    if 'WB' in selected_exp:
        p_t_fmt = "【{target}】のバンド強度を縦にペースト\n(例)\n15024\n14850\n..."
        p_l_fmt = "【{loading}】のバンド強度を縦にペースト\n(例)\n25010\n24800\n..."
    elif 'HPLC' in selected_exp:
        p_t_fmt = "【{target}】の定量値を縦にペースト\n(例)\n1.52\n1.48\n..."
        p_l_fmt = "【{loading}】を縦にペースト\n(例)\n0.85\n0.82\n..."
    elif 'qPCR' in selected_exp:
        p_t_fmt = "【{target}】のCt値を縦にペースト\n(例)\n25.4\n24.8\n..."
        p_l_fmt = "【{loading}】のCt値を縦にペースト\n(例)\n18.2\n18.5\n..."
    elif is_mtt_any:
        p_t_fmt, p_l_fmt = "", ""
    elif is_microscope:
        p_t_fmt = "【{target}】の細胞ごとの数値を縦にペースト\n(例)\n150.2\n148.5\n..."
        p_l_fmt = ""

    config = {
        'is_mtt': is_mtt_any, 
        'is_mtt_ic50': is_mtt_ic50,
        'ic50_fix_bottom': ic50_fix_bottom,
        'ic50_ctrl_gap': ic50_ctrl_gap,
        
        'show_mtt_bar': show_mtt_bar,
        'mtt_mock_col': mtt_mock_col,
        'mtt_bar_color': mtt_bar_color,
        'mtt_bar_width': mtt_bar_width,
        'mtt_bar_gap': mtt_bar_gap,
        'mtt_group_gap': mtt_group_gap,
        'mtt_outlier_mode': mtt_outlier_mode,
        
        'is_microscope': is_microscope, 'is_qpcr': is_qpcr, 'is_hplc': is_hplc,
        'microscope_stat': microscope_stat,
        'num_targets': num_targets, 'target_names': target_names, 'loading_names': loading_names,
        't_name': t_name, 'l_name': l_name, 'ylabel_input': ylabel_input,
        'error_bar_type': error_bar_type, 'layout_mode': layout_mode, 'color_mode': color_mode,
        'bar_width': bar_width_input, 'bar_gap': bar_gap_input, 'group_gap': group_gap_input, 'var_equal': var_equal, 'is_vs_control': is_vs_control,
        'y_tick_interval': y_tick_interval, 'svg_font_path': svg_font_path,
        'is_non_param': is_non_param, 'is_paired': is_paired, 'norm_mode': norm_mode,
        'is_grouped_test': is_grouped_test, 'u_label_name': u_label_name, 'd_label_name': d_label_name,
        'paste_t_label': paste_t_label, 'paste_l_label': paste_l_label,
        'show_stats': show_stats, 'label_style': label_style,
        'p_t_fmt': p_t_fmt, 'p_l_fmt': p_l_fmt,
        'is_common_loading': is_common_loading,
        'sigma_val': sigma_val, 'sens_val': sens_val, 'dist_val': dist_val, 'area_val': area_val, 'preview_color': preview_color,
        'fig_width': fig_width, 'fig_height': fig_height,
        'title_fontsize': title_fontsize, 'label_fontsize': label_fontsize,
        'tick_fontsize': tick_fontsize, 'x_label_fontsize': x_label_fontsize, 'legend_fontsize': legend_fontsize,
        'mtt_markers': mtt_markers, 'mtt_colors': mtt_colors
    }

    return config, num_cond