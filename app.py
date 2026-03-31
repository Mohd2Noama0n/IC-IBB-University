import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io

# --- إعدادات الصفحة ---
st.set_page_config(page_title="FMA Compaction Analyzer", layout="wide")

# --- دالة الحسابات الهندسية المطورة (بناءً على المعايرة الحقلية) ---
def calculate_field_compaction(n_passes, w_actual, w_opt, n_ref, c_ref_after, c_initial, efficiency):
    """
    حساب معامل الدمك لنقطة مجهولة بناءً على كفاءة المعدة ونتائج النقطة المرجعية.
    c_initial: معامل دمك التربة قبل مرور المعدة (Loose state).
    """
    eff_coeff = efficiency / 100.0
    
    # 1. تأثير الرطوبة (Penalty Factor)
    moisture_deviation = abs(w_actual - w_opt)
    moisture_factor = np.exp(-0.06 * moisture_deviation)
    
    # 2. حساب الطاقة النسبية المستهلكة في النقطة المجهولة مقابل المرجعية
    # يتم دمج الكفاءة هنا كعامل مؤثر في "قوة" كل دورة
    energy_target = n_passes * eff_coeff
    energy_ref = n_ref * eff_coeff
    
    if energy_ref == 0: return c_initial
    
    # 3. استنتاج معامل الدمك (نموذج النمو اللوغاريتمي للتربة)
    # الفرق بين الحالة الابتدائية والنهائية للمرجعية هو المقياس
    total_improvement_ref = c_ref_after - c_initial
    
    # نسبة التحسن بناءً على عدد الدورات الفعلي
    improvement_ratio = (np.log1p(energy_target) / np.log1p(energy_ref))
    
    compaction_result = c_initial + (total_improvement_ref * improvement_ratio * moisture_factor)
    
    return min(round(compaction_result, 2), 115.0)

# --- الواجهة الجانبية (Sidebar) ---
with st.sidebar:
    st.header("🏗️ إعدادات النظام والمشروع")
    
    with st.expander("📋 بيانات المشروع", expanded=True):
        proj_code = st.text_input("رمز المشروع", "FMA-2026-YEM")
        proj_loc = st.text_input("العنوان", "إب - اليمن")
        layer_no = st.number_input("رقم الطبقة", min_value=1, step=1)
        
    with st.expander("⚙️ نظام القياس والمعايرة"):
        target_min = st.number_input("معامل الدمك المطلوب الأدنى (%)", value=95.0)
        target_max = st.number_input("معامل الدمك المطلوب الأعلى (%)", value=100.0)
        omc = st.number_input("المحتوى الرطوبي الأمثل OMC (%)", value=12.0)
        
    with st.expander("🚜 بيانات المعدة"):
        machine_model = st.text_input("موديل المعدة", "CAT CS56B")
        efficiency = st.slider("كفاءة المعدة (مؤشر الأداء %)", 50, 120, 100)
        spacing = st.number_input("مسافة التباعد المطلوبة بين النقاط (متر)", value=5.0)

# --- الواجهة الرئيسية ---
st.title("📊 نظام مراقبة الدمك الهندسي (الربط المرجعي)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 النقطة المرجعية (GPS)")
    lat_ref = st.number_input("خط العرض (Latitude)", format="%.6f", value=13.9734)
    lon_ref = st.number_input("خط الطول (Longitude)", format="%.6f", value=44.1783)

with col2:
    st.subheader("🧪 نتائج المعايرة (Calibration)")
    c_initial = st.number_input("معامل الدمك الابتدائي (قبل الدك %)", value=80.0)
    n_ref = st.number_input("عدد دورات المرجعية المسجلة", value=8, min_value=1)
    c_ref_after = st.number_input("معامل دمك المرجعية (بعد الدك %)", value=98.5)
    w_ref_actual = st.number_input("الرطوبة الحقلية (%)", value=11.5)

st.divider()

# --- توليد النقاط بناءً على حركة المعدة بعد المعايرة ---
if st.button("🔄 بدء رصد المسار وتوليد نقاط الشبكة (GPS-Based)"):
    points = []
    # توليد نقاط بناءً على مصفوفة الحركة من النقطة المرجعية
    for x in range(-2, 3):
        for y in range(-2, 3):
            # حساب الإزاحة المكانية بناءً على مسافة التباعد (محاكاة حركة المعدة)
            dist_x = x * spacing
            dist_y = y * spacing
            p_lat = lat_ref + (dist_y / 111111)
            p_lon = lon_ref + (dist_x / (111111 * np.cos(np.radians(lat_ref))))
            
            # رصد عدد الدورات (simulated passes) بناءً على مرور المعدة
            # في الواقع، هذا الرقم يأتي من رصد تكرار الإحداثية، هنا نقوم بمحاكاته بذكاء
            sim_n = max(1, n_ref + np.random.randint(-3, 4)) 
            sim_w = w_ref_actual + np.random.uniform(-1.5, 1.5)
            
            # حساب معامل الدمك للنقطة المجهولة باستخدام دالة المعايرة وكفاءة المعدة
            comp_val = calculate_field_compaction(
                sim_n, sim_w, omc, n_ref, c_ref_after, c_initial, efficiency
            )
            
            status = "Passed" if target_min <= comp_val <= target_max else ("Over-compacted" if comp_val > target_max else "Failed")
            
            points.append({
                "Point ID": f"P({x},{y})",
                "Latitude": p_lat,
                "Longitude": p_lon,
                "Passes (n)": sim_n,
                "Moisture (%)": round(sim_w, 2),
                "Compaction (%)": comp_val,
                "Status": status
            })
    st.session_state.points_df = pd.DataFrame(points)

# --- العرض الجدولي والخرائط ---
if 'points_df' in st.session_state:
    df = st.session_state.points_df
    st.subheader("📋 سجل النقاط المرصودة حركياً")
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("🗺️ الخريطة الحرارية (تحليل حركة المعدة)")
    
    color_scale = [
        [0.0, "#ff0000"], [0.5, "#ffff00"], [0.9, "#1A9850"], [1.0, "#4B0082"]
    ]

    fig = px.density_mapbox(
        df, lat='Latitude', lon='Longitude', z='Compaction (%)',
        radius=50, center=dict(lat=lat_ref, lon=lon_ref), zoom=18,
        mapbox_style="carto-positron", color_continuous_scale=color_scale,
        range_color=[70, 110], title=f"Analysis: {proj_code} - Layer {layer_no}"
    )
    
    fig.add_annotation(dict(x=0.02, y=0.98, showarrow=False, text="↑ N", font=dict(size=24, color="black")))
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

    # --- التصدير ---
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Site_Compaction_Data', index=False)
        pd.DataFrame({
            "Parameter": ["Reference Passes", "Ref Compaction", "Machine Efficiency", "Initial State"],
            "Value": [n_ref, c_ref_after, f"{efficiency}%", c_initial]
        }).to_excel(writer, sheet_name='Calibration_Data')
    
    st.download_button("📥 تحميل التقرير الهندسي (Excel)", buffer.getvalue(), f"FMA_Report_{proj_code}.xlsx")
