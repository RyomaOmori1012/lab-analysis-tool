import streamlit as st
import traceback

from renderers.mtt import render_mtt_analysis
from renderers.single import render_single_target
from renderers.multi import render_multi_target
from ui_sidebar import setup_config
from ui_inputs import render_data_input

# ==========================================
# グローバル設定
# ==========================================
st.set_page_config(page_title="実験データ自動解析ツール v2.0", layout="wide")
st.title("🧪 実験データ自動解析ツール v2.0")

st.markdown("""
    <style>
    textarea {
        white-space: pre !important;
        overflow-wrap: normal !important;
        overflow-x: scroll !important;
    }
    div[data-testid="stExpander"] {
        border-color: #4ade80 !important;
    }
    /* 入力欄の隙間を極限まで詰める */
    .stTextInput { margin-bottom: -10px; }
    </style>
""", unsafe_allow_html=True)

# ★ 絶対に消えないデータ保護庫
if "data_dict" not in st.session_state:
    st.session_state.data_dict = {}

# ==========================================
# メイン実行関数
# ==========================================
def main():
    # 画面の列を先に作成
    col_input, col_graph = st.columns([1.2, 1.0], gap="large")

    # 1. サイドバーとターゲット設定を描画し、設定値をすべて受け取る
    config, num_cond = setup_config(col_input)

    # 2. 左側：データ入力フォームを描画して、入力されたデータを受け取る
    with col_input:
        input_data = render_data_input(config, num_cond)

    # 3. 右側：受け取ったデータと設定値をもとに、グラフを描画する
    with col_graph:
        st.header("📊 リアルタイムプレビュー")
        
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
