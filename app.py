import streamlit as st
import traceback
import json
import base64
import re
import time

# --- SVGの裏側から隠しデータを抽出する魔法の関数 ---
def extract_state_from_svg(svg_bytes):
    try:
        svg_str = svg_bytes.decode('utf-8', errors='ignore')
        match = re.search(r'<metadata id="app-state-data">(.*?)</metadata>', svg_str)
        if match:
            b64_str = match.group(1)
            json_str = base64.b64decode(b64_str).decode('utf-8')
            return json.loads(json_str)
    except Exception as e:
        st.error(f"復元データの読み込みエラー: {e}")
    return None

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
    
    /* 右側のグラフエリアをスクロール追従（Sticky）にする魔法のCSS */
    div[data-testid="column"]:last-of-type {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 4rem !important; 
        align-self: flex-start !important;
        z-index: 100 !important;
    }
    </style>
""", unsafe_allow_html=True)

if "data_dict" not in st.session_state:
    st.session_state.data_dict = {}

# ==========================================
# メイン実行関数
# ==========================================
def main():
    # --- ★ データの復元（ドラッグ＆ドロップ枠） ---
    st.sidebar.markdown("### 📂 データの復元 (SVGをD&D)")
    restore_file = st.sidebar.file_uploader("保存したSVGグラフをドロップして設定と数値を復元", type=["svg"], key="svg_uploader")
    
    if restore_file is not None:
        if st.session_state.get('last_uploaded_svg') != restore_file.file_id:
            with st.spinner("データを読み込み中..."):
                restored_data = extract_state_from_svg(restore_file.getvalue())
                if restored_data:
                    for k, v in restored_data.items():
                        if k != "svg_uploader" and "bulk_editor_widget" not in k:
                            st.session_state[k] = v
                    st.session_state['last_uploaded_svg'] = restore_file.file_id
                    # データを流し込んだら、入力欄に反映させるために1度だけ再起動
                    st.rerun()
                else:
                    st.sidebar.error("❌ このSVGファイルには復元データが含まれていません。")
                    st.session_state['last_uploaded_svg'] = restore_file.file_id
        
        # ★ 修正: 処理をストップ(st.stop)させず、メッセージだけを出して下の入力欄を描画させる！
        st.sidebar.success("✨ データの読み込みが完了しました！")
        st.sidebar.info("👉 **エラーを防ぐため、上の「×」ボタンを押してファイルをクリアしてください。**")
        st.sidebar.markdown("---")
    else:
        st.sidebar.markdown("---")

    # 画面の列を先に作成
    col_input, col_graph = st.columns([1.2, 1.0], gap="large")

    config, num_cond = setup_config(col_input)

    with col_input:
        input_data = render_data_input(config, num_cond)

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
