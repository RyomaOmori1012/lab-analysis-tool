import platform
import re
import json
import base64
import matplotlib.pyplot as plt
import streamlit as st

# --- フォントのグローバル設定（ローカルのこだわり維持 ＋ サーバー対策） ---
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Liberation Sans', 'Hiragino Sans', 'MS PGothic', 'IPAexGothic', 'sans-serif']

if platform.system() == 'Linux':
    plt.rcParams['mathtext.fontset'] = 'dejavusans'
else:
    plt.rcParams['mathtext.fontset'] = 'custom'
    plt.rcParams['mathtext.rm'] = 'Arial'
    plt.rcParams['mathtext.it'] = 'Arial:italic'
    plt.rcParams['mathtext.bf'] = 'Arial:bold'


def get_font(text):
    """テキスト内に1文字でも「日本語（全角文字）」が含まれているか判定する"""
    # 「μ」「µ」「°(度)」などは英語フォント(Arial)に含まれているため、日本語判定から除外する
    clean_text = re.sub(r'[μµ°]', '', str(text))
    
    if re.search(r'[^\x00-\x7F]', clean_text):
        if platform.system() == 'Linux':
            return 'IPAexGothic'      
        elif platform.system() == 'Darwin':
            return 'Hiragino Sans'    
        else:
            return 'MS PGothic'       
    else:
        return 'Liberation Sans' if platform.system() == 'Linux' else 'Arial'


def fix_svg_font(svg_bytes):
    """SVG出力時も、Mac用のHiraginoなどを追加してフォント崩れを防ぐ"""
    svg_str = svg_bytes.getvalue().decode('utf-8')
    svg_str = re.sub(r'font-family:[^;"]+', 'font-family: Arial, "Liberation Sans", "Hiragino Sans", "MS PGothic", "IPAexGothic", sans-serif', svg_str)
    return svg_str.encode('utf-8')


def embed_state_in_svg(svg_bytes):
    """SVGの裏側に全設定とデータを埋め込む魔法の関数"""
    try:
        svg_str = svg_bytes.decode('utf-8')
        safe_state = {}
        for k, v in st.session_state.items():
            if k == "svg_uploader": continue
            try:
                json.dumps(v)
                safe_state[k] = v
            except:
                pass
        json_str = json.dumps(safe_state)
        b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        metadata = f'<metadata id="app-state-data">{b64_str}</metadata>'
        svg_str = svg_str.replace('</svg>', f'\n{metadata}\n</svg>')
        return svg_str.encode('utf-8')
    except:
        return svg_bytes


def draw_significance_brackets(ax, sig_pairs, current_max_y, base_fs, text_offset_ratio=0.2, y_shift_ratio=0.15, h_ratio=0.025, bracket_lw=1.2):
    """
    有意差バー（ブラケット）を描画し、最大要素のy座標と描画された星のセットを返す。
    """
    if not sig_pairs:
        return current_max_y, set()
        
    y_shift = current_max_y * y_shift_ratio
    h = current_max_y * h_ratio
    base_bracket_y = current_max_y * 1.10
    max_element_y = current_max_y
    
    levels = []
    plotted_stars = set()
    
    for x_start, x_end, stars in sorted(sig_pairs, key=lambda x: x[1] - x[0]):
        plotted_stars.add(stars)
        
        placed_level = next((l_idx for l_idx, intervals in enumerate(levels) if not any(not (x_end < s or x_start > e) for s, e in intervals)), -1)
        if placed_level == -1: 
            placed_level = len(levels)
            levels.append([])
        
        levels[placed_level].append((x_start, x_end))
        by = base_bracket_y + placed_level * y_shift
        max_element_y = max(max_element_y, by + h)
        
        ax.plot([x_start, x_start, x_end, x_end], [by - h, by, by, by - h], color='black', lw=bracket_lw)
        text_y = by + h * text_offset_ratio
        ax.text((x_start + x_end) / 2, text_y, stars, ha='center', va='bottom', color='black', fontsize=base_fs, fontweight='bold', fontname='Arial')
        
    return max_element_y, plotted_stars