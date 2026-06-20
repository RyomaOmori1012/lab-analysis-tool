import numpy as np
import pandas as pd
from scipy import stats
from itertools import combinations
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import re
import io
from PIL import Image

# ==========================================
# 統計・計算用ヘルパー関数
# ==========================================
def calc_error(data, err_type):
    arr = np.array(data)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2: return 0.0
    sd = np.std(arr, ddof=1)
    return sd / np.sqrt(len(arr)) if "SEM" in err_type else sd

def welch_anova_games_howell(data_list):
    k = len(data_list)
    ns = np.array([len(d) for d in data_list])
    means = np.array([np.nanmean(d) for d in data_list])
    vars = np.array([np.nanvar(d, ddof=1) if len(d) > 1 else 1e-10 for d in data_list])
    vars = np.where(np.isnan(vars), 1e-10, vars)
    vars = np.where(vars <= 0, 1e-10, vars)
    
    w = ns / vars
    sum_w = np.sum(w)
    grand_mean = np.sum(w * means) / sum_w
    num = np.sum(w * (means - grand_mean)**2) / (k - 1)
    den_part = np.sum((1 - w / sum_w)**2 / (ns - 1))
    den = 1 + (2 * (k - 2) / (k**2 - 1)) * den_part
    f_val = num / den
    df1 = k - 1
    df2 = 1 / (3 / (k**2 - 1) * den_part)
    p_anova = stats.f.sf(f_val, df1, df2)
    
    pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            t_val = np.abs(means[i] - means[j]) / np.sqrt(vars[i]/ns[i] + vars[j]/ns[j])
            df_num = (vars[i]/ns[i] + vars[j]/ns[j])**2
            df_den = ((vars[i]/ns[i])**2) / (ns[i]-1) + ((vars[j]/ns[j])**2) / (ns[j]-1)
            df_gh = df_num / df_den if df_den > 0 else 1e-10
            q_val = t_val * np.sqrt(2)
            try:
                p_gh = stats.studentized_range.sf(q_val, k, df_gh)
            except AttributeError:
                p_gh = stats.t.sf(t_val, df_gh) * 2 * (k * (k - 1) / 2)
                p_gh = min(p_gh, 1.0)
            pairs.append((i, j, p_gh))
            
    return p_anova, pairs

def run_statistical_test(valid_data, var_equal, is_vs_control, is_non_param, is_paired):
    k = len(valid_data)
    pairs = []
    p_anova = np.nan
    test_name = ""
    
    if k < 2: return np.nan, [], ""
        
    if k == 2:
        d1, d2 = valid_data[0], valid_data[1]
        if is_non_param:
            if is_paired:
                if len(d1) != len(d2): return np.nan, [], "Wilcoxon failed (Size mismatch)"
                try: _, p_anova = stats.wilcoxon(d1, d2); test_name = "Wilcoxon signed-rank test"
                except: p_anova = np.nan
            else:
                try: _, p_anova = stats.mannwhitneyu(d1, d2, alternative='two-sided'); test_name = "Mann-Whitney U test"
                except: p_anova = np.nan
        elif is_paired:
            if len(d1) != len(d2): return np.nan, [], "Paired t-test failed (Size mismatch)"
            try: _, p_anova = stats.ttest_rel(d1, d2); test_name = "Paired t-test"
            except: p_anova = np.nan
        else:
            try: _, p_anova = stats.ttest_ind(d1, d2, equal_var=var_equal)
            except: p_anova = np.nan
            test_name = "Student's t-test" if var_equal else "Welch's t-test"
        if not np.isnan(p_anova):
            pairs.append((0, 1, p_anova))
            
    else: 
        if is_non_param:
            try: _, p_anova = stats.kruskal(*valid_data)
            except: p_anova = np.nan
            if not np.isnan(p_anova) and p_anova < 0.05:
                raw_p, comp_pairs = [], []
                test_name = "Kruskal-Wallis test followed by Mann-Whitney U test (Holm vs Control)" if is_vs_control else "Kruskal-Wallis test followed by Mann-Whitney U test (Holm)"
                iterator = range(1, k) if is_vs_control else combinations(range(k), 2)
                for idxs in iterator:
                    i, j = (0, idxs) if is_vs_control else idxs
                    try:
                        _, p = stats.mannwhitneyu(valid_data[i], valid_data[j], alternative='two-sided')
                        raw_p.append(p); comp_pairs.append((i, j))
                    except: pass
                if raw_p:
                    _, corrected_p, _, _ = multipletests(raw_p, method='holm')
                    pairs = [(comp_pairs[m][0], comp_pairs[m][1], corrected_p[m]) for m in range(len(raw_p))]
                    
        elif is_paired:
            lens = [len(d) for d in valid_data]
            if len(set(lens)) > 1: return np.nan, [], "Friedman test failed (Size mismatch)"
            try:
                _, p_anova = stats.friedmanchisquare(*valid_data)
                test_name = "Friedman test followed by Wilcoxon signed-rank test (Holm)" if not is_vs_control else "Friedman test followed by Wilcoxon (Holm vs Control)"
            except: return np.nan, [], "Friedman test failed"
                
            if not np.isnan(p_anova) and p_anova < 0.05:
                raw_p, comp_pairs = [], []
                iterator = range(1, k) if is_vs_control else combinations(range(k), 2)
                for idxs in iterator:
                    i, j = (0, idxs) if is_vs_control else idxs
                    try:
                        _, p = stats.wilcoxon(valid_data[i], valid_data[j])
                        raw_p.append(p); comp_pairs.append((i, j))
                    except: pass
                if raw_p:
                    _, corrected_p, _, _ = multipletests(raw_p, method='holm')
                    pairs = [(comp_pairs[m][0], comp_pairs[m][1], corrected_p[m]) for m in range(len(raw_p))]
                
        else:
            if var_equal:
                test_name = "One-way ANOVA followed by Student's t-test (Holm)" if is_vs_control else "One-way ANOVA followed by Tukey's test"
                try: _, p_anova = stats.f_oneway(*valid_data)
                except: p_anova = np.nan
                
                if not np.isnan(p_anova) and p_anova < 0.05:
                    if is_vs_control:
                        try:
                            from scipy.stats import dunnett
                            test_name = "One-way ANOVA followed by Dunnett's test"
                            res = dunnett(*valid_data[1:], control=valid_data[0])
                            p_vals = res.pvalue
                            if np.isscalar(p_vals):
                                p_vals = [p_vals]
                            for j in range(1, k):
                                pairs.append((0, j, p_vals[j-1]))
                        except (ImportError, AttributeError):
                            test_name = "One-way ANOVA followed by Student's t-test (Holm)"
                            raw_p, comp_pairs = [], []
                            for j in range(1, k):
                                try:
                                    _, p = stats.ttest_ind(valid_data[0], valid_data[j], equal_var=True)
                                    raw_p.append(p); comp_pairs.append((0, j))
                                except: pass
                            if raw_p:
                                _, corrected_p, _, _ = multipletests(raw_p, method='holm')
                                pairs = [(comp_pairs[m][0], comp_pairs[m][1], corrected_p[m]) for m in range(len(raw_p))]
                    else:
                        test_name = "One-way ANOVA followed by Tukey's test"
                        all_v, all_g = [], []
                        for p_idx, d in enumerate(valid_data):
                            all_v.extend(d)
                            all_g.extend([p_idx] * len(d))
                        try:
                            tukey = pairwise_tukeyhsd(all_v, all_g, alpha=0.05)
                            df_t = pd.DataFrame(data=tukey._results_table.data[1:], columns=tukey._results_table.data[0])
                            for _, row in df_t.iterrows():
                                pairs.append((int(row['group1']), int(row['group2']), row['p-adj']))
                        except: pass
            else:
                test_name = "Welch's ANOVA followed by Welch's t-test (Holm)" if is_vs_control else "Welch's ANOVA followed by Games-Howell test"
                try: p_anova, gh_pairs = welch_anova_games_howell(valid_data)
                except: p_anova = np.nan
                
                if not np.isnan(p_anova) and p_anova < 0.05:
                    if is_vs_control:
                        raw_p, comp_pairs = [], []
                        for j in range(1, k):
                            try:
                                _, p = stats.ttest_ind(valid_data[0], valid_data[j], equal_var=False)
                                raw_p.append(p); comp_pairs.append((0, j))
                            except: pass
                        if raw_p:
                            _, corrected_p, _, _ = multipletests(raw_p, method='holm')
                            pairs = [(comp_pairs[m][0], comp_pairs[m][1], corrected_p[m]) for m in range(len(raw_p))]
                    else:
                        pairs = gh_pairs
                        
    return p_anova, pairs, test_name

# ==========================================
# パーサー関数
# ==========================================
def parse_text(text):
    if not text.strip(): return [np.nan]
    res = []
    for line in text.replace(',', '\n').split('\n'):
        if line.strip():
            try: res.append(float(line.strip()))
            except ValueError: res.append(np.nan)
    return res if res else [np.nan]

def parse_plate(text):
    if not text.strip(): return np.full((8, 12), np.nan)
    lines = [line for line in text.replace('\r', '').split('\n')]
    data = []
    for line in lines:
        if not line.strip(): continue
        row = []
        parts = line.split('\t') if '\t' in line else re.sub(r'[\s,]+', ',', line.strip()).split(',')
        for x in parts:
            x = x.strip()
            if not x: row.append(np.nan)
            else:
                try: row.append(float(x))
                except ValueError: row.append(np.nan)
        while len(row) < 12: row.append(np.nan)
        data.append(row[:12])
    while len(data) < 8: data.append([np.nan] * 12)
    return np.array(data[:8])

def parse_idx(text, is_alpha=False):
    res = []
    try:
        for p in text.replace(' ', '').split(','):
            if not p: continue
            if '-' in p:
                start, end = p.split('-')
                if start and end: 
                    res.extend(range(ord(start.upper())-65, ord(end.upper())-65+1) if is_alpha else range(int(start)-1, int(end)))
            else: 
                res.append(ord(p.upper())-65 if is_alpha else int(p)-1)
    except Exception: pass 
    return list(set(res))

# ==========================================
# ★ 画像解析エンジン (AI爆速化・内訳出力対応)
# ==========================================
def analyze_images(uploaded_files, mode="standard", sigma=1.5, sensitivity=1.0, min_distance=20, min_area=200):
    all_intensities = []
    summary_details = []
    
    if mode == "ai":
        from cellpose import models, core
        from skimage import measure
        from skimage.transform import resize
        use_gpu = core.use_gpu()
        model = models.CellposeModel(gpu=use_gpu, model_type='cyto')
                
    for file in uploaded_files:
        file_bytes = file.getvalue()
        filename = file.name.lower()
        
        if filename.endswith('.czi'):
            try:
                import czifile
                with czifile.CziFile(io.BytesIO(file_bytes)) as czi:
                    img_array = czi.asarray()
                img_array = np.squeeze(img_array)
                if img_array.ndim > 2:
                    img_array = img_array[0]
                img_array = img_array.astype(np.float32)
            except Exception as e:
                raise RuntimeError(f"⚠️ CZI読み込みエラー ({file.name}): {e}")
        else:
            try:
                img = Image.open(io.BytesIO(file_bytes)).convert("L")
                img_array = np.array(img, dtype=np.float32)
            except Exception as e:
                raise RuntimeError(f"⚠️ 画像読み込みエラー ({file.name}): {e}")
                
        if mode == "standard":
            from skimage import filters, measure, segmentation, feature
            from scipy import ndimage
            
            blurred = filters.gaussian(img_array, sigma=sigma)
            thresh = filters.threshold_otsu(blurred)
            binary = blurred > (thresh * sensitivity)
            
            distance = ndimage.distance_transform_edt(binary)
            coords = feature.peak_local_max(distance, min_distance=min_distance, labels=binary)
            
            mask = np.zeros(distance.shape, dtype=bool)
            mask[tuple(coords.T)] = True
            markers, _ = ndimage.label(mask)
            labels = segmentation.watershed(-distance, markers, mask=binary)
            
            props = measure.regionprops(labels, intensity_image=img_array)
            intensities = [p.mean_intensity for p in props if p.area >= min_area]
            all_intensities.extend(intensities)
            summary_details.append(f"{file.name}: {len(intensities)}個")
            
        elif mode == "ai":
            try:
                h, w = img_array.shape
                max_dim = 1024
                if max(h, w) > max_dim:
                    scale = max_dim / max(h, w)
                    new_h, new_w = int(h * scale), int(w * scale)
                    img_resized = resize(img_array, (new_h, new_w), preserve_range=True, anti_aliasing=True).astype(np.float32)
                    masks_resized, flows, styles = model.eval(img_resized, diameter=None, channels=[0,0])
                    masks = resize(masks_resized, (h, w), order=0, preserve_range=True, anti_aliasing=False).astype(np.uint16)
                else:
                    masks, flows, styles = model.eval(img_array, diameter=None, channels=[0,0])
                
                props = measure.regionprops(masks, intensity_image=img_array)
                intensities = [p.mean_intensity for p in props if p.area >= 100]
                all_intensities.extend(intensities)
                summary_details.append(f"{file.name}: {len(intensities)}個")
            except Exception as e:
                raise RuntimeError(f"⚠️ AI解析エラー ({file.name}): {e}")
                
    return all_intensities, " / ".join(summary_details)

# ==========================================
# ★ プレビュー画像生成（自動判別・完全復元版）
# ==========================================
def generate_preview_image(file_bytes, filename, mode="standard", sigma=1.5, sensitivity=1.0, min_distance=20, min_area=200, preview_color="自動 (メタデータから判別)"):
    # デフォルトは白黒（そのままの色）
    r_usr, g_usr, b_usr = 1.0, 1.0, 1.0 
    is_auto = "自動" in preview_color
    
    if not is_auto:
        color_map = {
            "緑 (Green)": (0.0, 1.0, 0.0),
            "赤 (Red)": (1.0, 0.0, 0.0),
            "青 (Blue)": (0.0, 0.0, 1.0),
            "シアン (Cyan)": (0.0, 1.0, 1.0),
            "マゼンタ (Magenta)": (1.0, 0.0, 1.0),
            "白黒 (Gray)": (1.0, 1.0, 1.0)
        }
        r_usr, g_usr, b_usr = color_map.get(preview_color, (1.0, 1.0, 1.0))

    if filename.endswith('.czi'):
        try:
            import czifile
            import re
            
            with czifile.CziFile(io.BytesIO(file_bytes)) as czi:
                img_array = czi.asarray()
                meta_xml = czi.metadata()
                
            img_array = np.squeeze(img_array)
            if img_array.ndim > 2:
                img_array = img_array[0]
            img_array = img_array.astype(np.float32)
            img_gray = img_array
            
            if is_auto:
                # ★ CZIの自動判別ロジック（復元）
                r_mult, g_mult, b_mult = 1.0, 1.0, 1.0 # fallback
                if isinstance(meta_xml, str):
                    match = re.search(r'<Color>([^<]+)</Color>', meta_xml, re.IGNORECASE)
                    if match:
                        val = match.group(1).strip()
                        if val.startswith('#'):
                            h_val = val.lstrip('#')
                            if len(h_val) == 8:
                                r_mult, g_mult, b_mult = int(h_val[2:4], 16)/255.0, int(h_val[4:6], 16)/255.0, int(h_val[6:8], 16)/255.0
                            elif len(h_val) == 6:
                                r_mult, g_mult, b_mult = int(h_val[0:2], 16)/255.0, int(h_val[2:4], 16)/255.0, int(h_val[4:6], 16)/255.0
                        else:
                            try:
                                argb_int = int(val)
                                h_val = f"{argb_int & 0xFFFFFFFF:08x}"
                                r_mult, g_mult, b_mult = int(h_val[2:4], 16)/255.0, int(h_val[4:6], 16)/255.0, int(h_val[6:8], 16)/255.0
                            except: pass
                    else:
                        if re.search(r'GFP|Alexa.*488|FITC|Green|Fluo-4', meta_xml, re.IGNORECASE): r_mult, g_mult, b_mult = 0.0, 1.0, 0.0
                        elif re.search(r'RFP|mCherry|Alexa.*594|Texas.*Red|Red|Cy3', meta_xml, re.IGNORECASE): r_mult, g_mult, b_mult = 1.0, 0.0, 0.0
                        elif re.search(r'DAPI|Hoechst|Blue|Alexa.*405', meta_xml, re.IGNORECASE): r_mult, g_mult, b_mult = 0.0, 0.0, 1.0
            else:
                # マニュアル指定
                r_mult, g_mult, b_mult = r_usr, g_usr, b_usr
            
            img_min, img_max = img_array.min(), img_array.max()
            img_norm = (img_array - img_min) / (img_max - img_min + 1e-10)
            img_rgb_bg = np.stack((img_norm * r_mult, img_norm * g_mult, img_norm * b_mult), axis=-1)
            
        except Exception as e:
            raise RuntimeError(f"CZI読み込みエラー: {e}")
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img_gray = np.array(img.convert("L"), dtype=np.float32)
            
            if img.mode in ['RGB', 'RGBA'] and is_auto:
                # 元がカラー画像で自動指定ならそのまま使う
                img_rgb_bg = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
            else:
                img_min, img_max = img_gray.min(), img_gray.max()
                img_norm = (img_gray - img_min) / (img_max - img_min + 1e-10)
                
                # 自動指定なら白黒のまま、手動指定ならその色に塗る
                r_mult, g_mult, b_mult = (1.0, 1.0, 1.0) if is_auto else (r_usr, g_usr, b_usr)
                img_rgb_bg = np.stack((img_norm * r_mult, img_norm * g_mult, img_norm * b_mult), axis=-1)
        except Exception as e:
            raise RuntimeError(f"画像読み込みエラー: {e}")
            
    if mode == "standard":
        from skimage import filters, measure, segmentation, feature
        from scipy import ndimage
        
        blurred = filters.gaussian(img_gray, sigma=sigma)
        thresh = filters.threshold_otsu(blurred)
        binary = blurred > (thresh * sensitivity)
        
        distance = ndimage.distance_transform_edt(binary)
        coords = feature.peak_local_max(distance, min_distance=min_distance, labels=binary)
        
        mask = np.zeros(distance.shape, dtype=bool)
        mask[tuple(coords.T)] = True
        markers, _ = ndimage.label(mask)
        labels = segmentation.watershed(-distance, markers, mask=binary)
        
        props = measure.regionprops(labels, intensity_image=img_gray)
        valid_labels = np.array([p.label for p in props if p.area >= min_area])
        final_labels = np.where(np.isin(labels, valid_labels), labels, 0)
        
        # 輪郭線は黄色(1, 1, 0)で描画
        overlay = segmentation.mark_boundaries(img_rgb_bg, final_labels, color=(1, 1, 0), mode='thick')
        return overlay, len(valid_labels)
        
    elif mode == "ai":
        from cellpose import models, core
        from skimage import measure, segmentation
        from skimage.transform import resize
        
        use_gpu = core.use_gpu()
        model = models.CellposeModel(gpu=use_gpu, model_type='cyto')
        
        h, w = img_gray.shape
        max_dim = 1024
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_h, new_w = int(h * scale), int(w * scale)
            img_resized = resize(img_gray, (new_h, new_w), preserve_range=True, anti_aliasing=True).astype(np.float32)
            masks_resized, flows, styles = model.eval(img_resized, diameter=None, channels=[0,0])
            masks = resize(masks_resized, (h, w), order=0, preserve_range=True, anti_aliasing=False).astype(np.uint16)
        else:
            masks, flows, styles = model.eval(img_gray, diameter=None, channels=[0,0])
        
        props = measure.regionprops(masks, intensity_image=img_gray)
        valid_labels = np.array([p.label for p in props if p.area >= 100])
        
        final_labels = np.where(np.isin(masks, valid_labels), masks, 0)
        # AIモードの輪郭線は水色(0, 1, 1)で描画
        overlay = segmentation.mark_boundaries(img_rgb_bg, final_labels, color=(0, 1, 1), mode='thick')
        return overlay, len(valid_labels)
