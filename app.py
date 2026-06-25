import streamlit as st
import traceback
import json
import base64
import re
import time
import platform  # ←追加

# --- 【超重要】URL版(Linux)で追加したフォントが反映されない問題(キャッシュ)を自動修復 ---
if platform.system() == 'Linux':
    import matplotlib.font_manager as fm
    # 'Liberation Sans' がサーバーの記憶(キャッシュ)にない場合のみ、記憶を消して再スキャンする
    if not any('Liberation Sans' in f.name for f in fm.fontManager.ttflist):
        import matplotlib as mpl
        import os
        import shutil
        cache_dir = mpl.get_cachedir()
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
        fm._load_fontmanager(try_read_cache=False)

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
from renderers.mtt_ic50 import render_mtt_ic50
from renderers.microscope import render_microscope_analysis
from ui_sidebar import setup_config
from ui_inputs import render_data_input

# ==========================================
# グローバル設定
# ==========================================
st.set_page_config(page_title="実験データ自動解析ツール v2.0", layout="wide")
st.title("🧪 実験データ自動解析ツール v2.0")

st.markdown("""
    <style>
    /* テキストエリアの横スクロール維持 */
    textarea {
        white-space: pre !important;
        overflow-wrap: normal !important;
        overflow-x: scroll !important;
    }
    
    /* サイドバーの上部余白調整 */
    div[data-testid="stSidebarUserContent"] {
        padding-top: 1rem;
    }

    /* =========================================================
       🚀 グラフエリアのSticky（追従）を強制発動させる最終奥義
       ========================================================= */
       
    /* 1. 親要素(左右カラムのコンテナ)の「高さ強制引き伸ばし」を解除し、上揃えにする */
    div[data-testid="stHorizontalBlock"] {
        align-items: flex-start !important;
    }

    /* 2. 右カラム（2番目のカラム）を狙い撃ちしてStickyをかける */
    div[data-testid="stColumn"]:nth-of-type(2) {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 3rem !important; /* 画面上部からの停止位置 */
        height: max-content !important; /* ★超重要：高さを中身ピッタリに収めてスライドのスキマを作る */
        z-index: 999 !important;
    }
    </style>
""", unsafe_allow_html=True)

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = {}

def main():
    st.sidebar.header("📁 データの復元 (オプション)")
    uploaded_svg = st.sidebar.file_uploader("前回保存したSVGファイルをアップロードしてデータを復元:", type=['svg'], key="svg_uploader")
    
    if uploaded_svg is not None:
        if 'last_uploaded_svg' not in st.session_state or st.session_state['last_uploaded_svg'] != uploaded_svg.file_id:
            with st.spinner("データを復元中..."):
                time.sleep(0.5)
                restored_state = extract_state_from_svg(uploaded_svg.getvalue())
                if restored_state:
                    for k, v in restored_state.items():
                        # ★ 修正ポイント: 表パーツに加えて、画像アップローダー(imgs_)の痕跡も復元をスキップする！
                        if k.startswith("bulk_editor_widget_") or k.startswith("imgs_"):
                            continue
                        st.session_state[k] = v
                    st.session_state['last_uploaded_svg'] = uploaded_svg.file_id
                    st.sidebar.success("✨ 復元成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.sidebar.error("⚠️ 復元データが含まれていません。")
                    st.session_state['last_uploaded_svg'] = uploaded_svg.file_id
        
        st.sidebar.info("👉 **エラーを防ぐため、上の「×」ボタンを押してファイルをクリアしてください。**")
        st.sidebar.markdown("---")
    else:
        st.sidebar.markdown("---")

    col_input, col_graph = st.columns([1.2, 1.0], gap="large")

    config, num_cond = setup_config(col_input)

    with col_input:
        input_data = render_data_input(config, num_cond)

    with col_graph:
        st.header("📊 リアルタイムプレビュー")
        
        try:
            if config.get('is_mtt_ic50', False):
                render_mtt_ic50(input_data, config)
            elif config['is_mtt']:
                render_mtt_analysis(input_data, config)
            elif config['is_microscope']: 
                render_microscope_analysis(input_data, config)
            elif config['num_targets'] == 1:
                render_single_target(input_data, config)
            else:
                render_multi_target(input_data, config)
                
            if config.get('is_mtt', False) and config.get('show_mtt_bar', False):
                from renderers.mtt_bar import render_mtt_bar
                render_mtt_bar(input_data, config)
                
        except Exception as e:
            st.error(f"グラフ描画エラー: データが正しく入力されているか確認してください。\n詳細: {e}")
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()