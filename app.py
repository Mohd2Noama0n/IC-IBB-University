import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from datetime import datetime
import math
import warnings
# إضافة مكتبة جلب الموقع
from streamlit_js_eval import streamlit_js_eval 

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(page_title="FMA Compaction Analyzer Pro", layout="wide", initial_sidebar_state="expanded")

# ----------------------------- الدوال الهندسية الأساسية (جوهر الكود الأصلي) -----------------------------
def calculate_compaction_modulus(
    current_passes: int,
    current_moisture: float,
    reference_passes: int,
    reference_compaction_before: float,
    reference_compaction_after: float,
    optimum_moisture: float,
    machine_efficiency: float,
    initial_compaction: float
) -> float:
    effective_efficiency = machine_efficiency / 100.0
    energy_current = math.log1p(current_passes * effective_efficiency)
    energy_reference = math.log1p(reference_passes * effective_efficiency)
    
    if energy_reference <= 0:
        energy_ratio = 1.0
    else:
        energy_ratio = min(energy_current / energy_reference, 1.5)
    
    moisture_deviation = abs(current_moisture - optimum_moisture)
    moisture_factor = math.exp(-0.06 * moisture_deviation)
    moisture_factor = max(0.7, min(1.0, moisture_factor))
    
    total_improvement_reference = reference_compaction_after - reference_compaction_before
    current_improvement = total_improvement_reference * energy_ratio * moisture_factor
    
    compaction_modulus = initial_compaction + current_improvement
    return round(min(compaction_modulus, 110.0), 2)

def generate_heatmap_colors(compaction_value: float) -> str:
    if compaction_value < 50: return "#8B0000"
    elif compaction_value < 60: return "#FF0000"
    elif compaction_value < 70: return "#FF4500"
    elif compaction_value < 80: return "#FFA500"
    elif compaction_value < 85: return "#FFD700"
    elif compaction_value < 90: return "#FFFF00"
    elif compaction_value < 95: return "#ADFF2F"
    elif compaction_value < 100: return "#32CD32"
    elif compaction_value < 105: return "#228B22"
    elif compaction_value < 110: return "#1E90FF"
    else: return "#00008B"

# ----------------------------- واجهة المستخدم -----------------------------
with st.sidebar:
    st.markdown("## 🏗️ نظام الدمك الذكي FMA")
    st.markdown("---")
    
    # جلب إحداثيات GPS الحقيقية في الخلفية
    st.subheader("📍 نظام التتبع اللحظي")
    loc = streamlit_js_eval(js_expressions='done(window.navigator.geolocation.getCurrentPosition(success => done(success.coords)))', key='GPS_TRACKER')
    
    if loc:
        curr_lat = loc['latitude']
        curr_lon = loc['longitude']
        st.success(f"إشارة GPS نشطة: {curr_lat:.5f}")
    else:
        st.warning("جاري البحث عن الأقمار الصناعية...")
        curr_lat, curr_lon = 13.9633, 44.5819

    with st.expander("📋 بيانات المشروع", expanded=False):
        project_code = st.text_input("رمز المشروع", value="FMA-2026-001")
        project_address = st.text_input("العنوان", value="إب - اليمن")
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1)

    with st.expander("⚙️ معاملات التربة", expanded=True):
        optimum_moisture_content = st.number_input("المحتوى الرطوبي الأمثل OMC (%)", value=12.5)
        target_compaction_min = st.number_input("الحد الأدنى المستهدف (%)", value=95.0)
        machine_efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)

    st.markdown("---")
    st.caption("© FMA Intelligent Compaction System v2.0")

st.title("📊 FMA - رصد الدمك الميداني التلقائي")

tab1, tab2 = st.tabs(["🚀 الرصد الميداني اللحظي", "📉 التقارير والتحليل"])

with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📝 إدخال نقطة الرصد")
        current_passes = st.number_input("عدد الدورات الحالية", 1, 30, 8)
        current_moisture = st.number_input("الرطوبة الحقلية الحالية %", 5.0, 25.0, 12.0)
        
        # بيانات المعايرة (يمكن تثبيتها برمجياً أو جعلها مدخلات)
        ref_p = 8; ref_before = 78.0; ref_after = 98.5
        
        if st.button("💾 تسجيل وحساب النقطة الآن", type="primary", use_container_width=True):
            res = calculate_compaction_modulus(
                current_passes, current_moisture, ref_p, ref_before, ref_after,
                optimum_moisture_content, machine_efficiency, ref_before
            )
            
            new_record = {
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Latitude": curr_lat,
                "Longitude": curr_lon,
                "Passes": current_passes,
                "Moisture": current_moisture,
                "Compaction": res,
                "Status": "🟢 مقبول" if res >= target_compaction_min else "🔴 مرفوض"
            }
            
            if 'fma_records' not in st.session_state:
                st.session_state['fma_records'] = []
            st.session_state['fma_records'].append(new_record)
            st.toast(f"تم حفظ النقطة بمعامل دمك {res}%")

    with col2:
        st.subheader("🗺️ خريطة الرصد الميداني")
        if 'fma_records' in st.session_state and len(st.session_state['fma_records']) > 0:
            df = pd.DataFrame(st.session_state['fma_records'])
            
            fig = px.scatter_mapbox(df, lat="Latitude", lon="Longitude", color="Compaction",
                                    hover_data=["Time", "Passes", "Status"],
                                    color_continuous_scale="RdYlGn", 
                                    range_color=[80, 100], zoom=17,
                                    mapbox_style="carto-positron")
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df.tail(5), use_container_width=True)
        else:
            st.info("قم بتسجيل أول نقطة لعرض الخريطة الميدانية")

with tab2:
    if 'fma_records' in st.session_state:
        st.subheader("📈 تحليل جودة الطبقة")
        df_all = pd.DataFrame(st.session_state['fma_records'])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("عدد النقاط", len(df_all))
        c2.metric("متوسط الدمك", f"{df_all['Compaction'].mean():.1f}%")
        c3.metric("نسبة النجاح", f"{(df_all['Compaction'] >= target_compaction_min).mean()*100:.1f}%")
        
        # زر التصدير لـ Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_all.to_excel(writer, index=False)
        st.download_button("📥 تحميل التقرير الختامي لشركة FMA", output.getvalue(), 
                           file_name=f"FMA_Report_{project_code}.xlsx", use_container_width=True)
