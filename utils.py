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
                try: _, p_anova = stats.f_oneway(*valid_data)
                except: p_anova = np.nan
                
                if not np.isnan(p_anova) and p_anova < 0.05:
                    if is_vs_control:
                        # ★ここがDunnett検定の発動ポイントです★
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
                            # 古い環境でDunnettが入っていない場合の安全装置
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
# ★ 画像解析エンジン (マイルド・チューニング版 + AI最新版対応)
# ==========================================
def analyze_images(uploaded_files, mode="standard"):
    """アップロードされた複数画像を解析し、蛍光強度のリストを返す"""
    all_intensities = []
    
    for file in uploaded_files:
        file_bytes = file.read()
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
                raise RuntimeError(f"⚠️ CZIファイルの読み込みに失敗しました ({file.name})。詳細: {e}")
        else:
            try:
                img = Image.open(io.BytesIO(file_bytes)).convert("L")
                img_array = np.array(img)
            except Exception as e:
                raise RuntimeError(f"⚠️ 画像ファイルの読み込みに失敗しました ({file.name})。詳細: {e}")
                
        if mode == "standard":
            from skimage import filters, measure, segmentation, feature
            from scipy import ndimage
            
            blurred = filters.gaussian(img_array, sigma=5)
            thresh = filters.threshold_otsu(blurred)
            
            binary = blurred > (thresh * 1.1)
            
            distance = ndimage.distance_transform_edt(binary)
            coords = feature.peak_local_max(distance, min_distance=30, labels=binary)
            
            mask = np.zeros(distance.shape, dtype=bool)
            mask[tuple(coords.T)] = True
            markers, _ = ndimage.label(mask)
            labels = segmentation.watershed(-distance, markers, mask=binary)
            
            props = measure.regionprops(labels, intensity_image=img_array)
            intensities = [p.mean_intensity for p in props if p.area >= 600]
            all_intensities.extend(intensities)
            
        elif mode == "ai":
            try:
                from cellpose import models
                from skimage import measure
                model = models.CellposeModel(gpu=False, model_type='cyto')
                masks, flows, styles = model.eval(img_array, diameter=None, channels=[0,0])
                
                props = measure.regionprops(masks, intensity_image=img_array)
                intensities = [p.mean_intensity for p in props if p.area >= 100]
                all_intensities.extend(intensities)
            except Exception as e:
                raise RuntimeError(f"⚠️ AI解析中にエラーが発生しました: {e}")
                
    return all_intensities
