import streamlit as st

def setup_config(col_input):
    st.sidebar.header("⚙️ 全体設定")
    selected_exp = st.sidebar.selectbox('実験手法:', ['Western Blotting (WB)', 'HPLC', 'qPCR', 'MTT Assay (細胞生存率)', '蛍光顕微鏡 (Box Plot)'], key='selected_exp')
    num_cond = st.sidebar.number_input('手動モード時の条件数:', min_value=1, max_value=20, value=2, step=1, key='num_cond')

    is_mtt = 'MTT' in selected_exp
    is_microscope = '顕微鏡' in selected_exp
    is_qpcr = 'qPCR' in selected_exp
    is_hplc = 'HPLC' in selected_exp
    is_multi_capable = 'WB' in selected_exp or is_qpcr or is_hplc

    num_targets = st.sidebar.number_input('ターゲットの数 (1つのグラフにまとめる数):', min_value=1, max_value=10, value=1, step=1, key='num_targets') if is_multi_capable else 1

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

    with col_input:
        st.header("🎯 ターゲット設定")
        if num_targets == 1:
            c_t, c_l = st.columns(2)
            with c_t: t_name_raw = st.text_input(t_label, placeholder=t_ph, key='t_name_raw_0').strip()
            with c_l: l_name_raw = st.text_input(l_label, placeholder=l_ph, key='l_name_raw_0').strip() if not is_microscope else ""
            target_names.append(t_name_raw or ("Cell Line" if is_mtt else "Target"))
            loading_names.append(l_name_raw or ("Drug" if is_mtt else ("" if is_microscope else "Loading Control")))
        else:
            if not is_mtt and not is_microscope:
                is_common_loading = "共通" in st.radio("Loading Controlの扱い:", ["共通 (全てのターゲットで同じデータを使用)", "ターゲットごとに個別"], horizontal=True, key='is_common_loading_radio')
                if is_common_loading:
                    l_name_raw = st.text_input(f'共通の {l_label}', placeholder=l_ph, key='l_name_raw_com').strip()
                    loading_names = [l_name_raw or "Loading Control"] * num_targets
            
            for i in range(num_targets):
                if not is_common_loading and not is_mtt and not is_microscope:
                    c_t, c_l = st.columns(2)
                    with c_t: target_names.append(st.text_input(f'{t_label} {i+1}:', placeholder=f'Target {i+1}', key=f't_name_raw_{i+1}').strip() or f"Target {i+1}")
                    with c_l: loading_names.append(st.text_input(f'{l_label} {i+1}:', placeholder=f'Loading {i+1}', key=f'l_name_raw_{i+1}').strip() or f"Loading {i+1}")
                else:
                    target_names.append(st.text_input(f'{t_label} {i+1}:', placeholder=f'Target {i+1}', key=f't_name_raw_{i+1}').strip() or f"Target {i+1}")
                    if is_mtt: loading_names.append("Drug")
                    elif is_microscope: loading_names.append("")

    t_name = target_names[0]
    l_name = loading_names[0] if loading_names else ("Drug" if is_mtt else "" if is_microscope else "Loading Control")
    y_label_full = y_label_def if (is_mtt or is_microscope or is_hplc or num_targets > 1) else f"{y_label_def}\n[{t_name} / {l_name}]"
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 グラフ・軸設定**")
    # ★ 修正: Y軸ラベルがターゲット名に自動連動するよう、記憶用ID(key)を削除しました！
    ylabel_input = st.sidebar.text_area('Y軸ラベル:', value=y_label_full, height=68)

    if is_microscope:
        st.sidebar.markdown("---")
        with st.sidebar.expander("❓ 調整のコツ（何が変わるの？）", expanded=False):
            st.markdown("""
            プレビュー画像の**「黄色の輪郭線」**を見ながら調整してください。

            * **1. ぼかしの強さ (Sigma)**
            画像を滑らかにして細かいノイズを消します。数値を上げすぎると隣り合う細胞がくっついてしまいます。
            * **2. 閾値の感度 (Sensitivity)**
            細胞として認識する「明るさの基準」です。数値を下げると暗い細胞も拾いますが、背景のモヤモヤも拾いやすくなります。
            * **3. 細胞間の最小距離 (ピクセル)**
            細胞同士を区切る距離です。細胞が密集していて1つに繋がってしまう場合は「小さく」、1つの細胞が細かく分割されてしまう場合は「大きく」します。
            * **4. 細胞の最小サイズ (ピクセル)**
            指定したピクセルより小さいものは「ゴミ（死細胞や破片など）」として除外されます。
            """)
        with st.sidebar.expander("🔬 画像解析パラメータ (標準モード用)", expanded=False):
            preview_color = st.selectbox("🎨 プレビューの表示色:", ["自動 (メタデータから判別)", "緑 (Green)", "赤 (Red)", "青 (Blue)", "シアン (Cyan)", "マゼンタ (Magenta)", "白黒 (Gray)"], key='preview_color')
            sigma_val = st.slider("1. ぼかしの強さ (Sigma):", min_value=0.5, max_value=10.0, value=1.5, step=0.5, key='sigma_val')
            sens_val = st.slider("2. 閾値の感度 (Sensitivity):", min_value=0.5, max_value=2.0, value=1.0, step=0.1, key='sens_val')
            dist_val = st.slider("3. 細胞間の最小距離 (ピクセル):", min_value=5, max_value=150, value=20, step=5, key='dist_val')
            area_val = st.slider("4. 細胞の最小サイズ (ピクセル):", min_value=10, max_value=2000, value=200, step=10, key='area_val')
    else:
        preview_color = "自動 (メタデータから判別)"
        sigma_val, sens_val, dist_val, area_val = 1.5, 1.0, 20, 200

    st.sidebar.markdown("---")
    st.sidebar.header("🖌️ レイアウト・統計設定")

    show_stats = st.sidebar.toggle("統計結果（★）をグラフに表示する", value=True, key='show_stats')
    
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
            
            if not is_mtt:
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
    svg_font_path = st.sidebar.checkbox("SVG文字のアウトライン化 (パワポズレ防止)", value=True, key='svg_font_path', help="パワポ等の別ソフトに貼り付けた際のレイアウト崩れを防ぎます。パワポ上で文字を打ち直したい場合のみチェックを外してください。")

    mtt_markers = []
    mtt_colors = []

    if not is_mtt:
        with st.sidebar.expander("📊 グラフの基本レイアウト", expanded=False):
            layout_mode = "条件ごとにグループ化" if num_targets > 1 else st.radio("棒の配置:", ["条件ごとにグループ化", "均等に並べる"], key='layout_mode_radio')
            if num_targets > 1: st.info("💡 複数ターゲットモードでは、棒の配置は自動的に「ターゲット毎のグループ化」になります。")
            
            label_style = st.radio("X軸ラベルの表示形式:", ["1段 ＋ 系列名（凡例）", "横ラベルを2段にする（上下段）"], key='label_style_radio')
            color_mode = st.radio("棒の配色:", ["色分け", "すべて黒"], key='color_mode_radio')
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
                    sel_m = st.selectbox(f"マーカー {i+1}:", marker_keys, index=0, key=f"mtt_m_{i}", label_visibility="collapsed")
                    mtt_markers.append(marker_options[sel_m])
                with c2:
                    sel_c = st.selectbox(f"色 {i+1}:", color_keys, index=i % len(color_keys), key=f"mtt_c_{i}", label_visibility="collapsed")
                    mtt_colors.append(color_options[sel_c])

    st.sidebar.markdown("---")
    st.sidebar.header("🎨 グラフ詳細デザイン調整")
    with st.sidebar.expander("文字サイズ・グラフ幅・棒の微調整", expanded=False):
        st.info("💡 横幅を「0」にするとデータ数に合わせて自動調整されます。")
        fig_width = st.slider("グラフの横幅 (0で自動):", min_value=0.0, max_value=30.0, value=0.0, step=0.5, key='fig_width')
        fig_height = st.slider("グラフの縦幅:", min_value=3.0, max_value=20.0, value=5.0, step=0.5, key='fig_height')
        title_fontsize = st.slider("タイトルの文字サイズ:", min_value=8, max_value=36, value=14, step=1, key='title_fontsize')
        label_fontsize = st.slider("軸ラベル(Y軸等)の文字サイズ:", min_value=8, max_value=36, value=16, step=1, key='label_fontsize')
        
        if not is_mtt:
            tick_fontsize = st.slider("目盛り(数値)の文字サイズ:", min_value=8, max_value=36, value=14, step=1, key='tick_fontsize')
            x_label_fontsize = st.slider("横ラベル(条件名等)の文字サイズ:", min_value=8, max_value=36, value=14, step=1, key='x_label_fontsize')
        else:
            tick_fontsize = st.slider("縦横の目盛り(数値)の文字サイズ:", min_value=8, max_value=36, value=12, step=1, key='tick_fontsize')
            x_label_fontsize = 14

        legend_fontsize = st.slider("凡例の文字サイズ:", min_value=8, max_value=36, value=12, step=1, key='legend_fontsize')
        
        st.markdown("---")
        default_y_tick = 20.0 if is_mtt else 0.0
        y_tick_interval = st.number_input("縦軸(Y軸)の目盛り間隔 (0で自動):", min_value=0.0, max_value=1000000.0, value=default_y_tick, step=0.1, key='y_tick_interval')

        if not is_mtt:
            st.markdown("---")
            bar_width_input = st.slider("棒の太さ調整:", min_value=0.05, max_value=0.80, value=(0.25 if layout_mode == "条件ごとにグループ化" else 0.17), step=0.01, key='bar_width_input')
            if layout_mode == "条件ごとにグループ化":
                bar_gap_input = st.slider("グループ内の棒の間隔:", min_value=0.0, max_value=1.50, value=0.02, step=0.01, key='bar_gap_input_g')
                group_gap_input = st.slider("グループ間の間隔:", min_value=0.0, max_value=3.00, value=0.50, step=0.05, key='group_gap_input_g')
            else:
                bar_gap_input = st.slider("棒の間隔調整:", min_value=0.0, max_value=1.50, value=0.50, step=0.01, key='bar_gap_input_s')
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
    elif is_mtt:
        p_t_fmt, p_l_fmt = "", ""
    elif is_microscope:
        p_t_fmt = "【{target}】の細胞ごとの数値を縦にペースト\n(例)\n150.2\n148.5\n..."
        p_l_fmt = ""

    config = {
        'is_mtt': is_mtt, 'is_microscope': is_microscope, 'is_qpcr': is_qpcr, 'is_hplc': is_hplc,
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
