"""
================================================================================
FMA COMPACTION ANALYZER PRO - الإصدار المصحح
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import datetime
import math
import warnings
from streamlit_js_eval import streamlit_js_eval
import time

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction Analyzer Pro",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------- تهيئة حالة الجلسة -----------------------------
def init_session_state():
    """تهيئة جميع متغيرات الجلسة"""
    if 'fma_records' not in st.session_state:
        st.session_state.fma_records = []
    if 'reference_set' not in st.session_state:
        st.session_state.reference_set = False
    if 'reference_data' not in st.session_state:
        st.session_state.reference_data = {}
    if 'tracking_active' not in st.session_state:
        st.session_state.tracking_active = False
    if 'last_location' not in st.session_state:
        st.session_state.last_location = None

init_session_state()

# ----------------------------- الدوال الهندسية الأساسية -----------------------------
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
    """حساب معامل الدمك"""
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
    return round(min(compaction_modulus, 112.0), 2)


def get_compaction_color(compaction_value: float) -> str:
    """تحديد اللون حسب قيمة معامل الدمك"""
    if compaction_value < 50:
        return "#8B0000"
    elif compaction_value < 60:
        return "#FF0000"
    elif compaction_value < 70:
        return "#FF4500"
    elif compaction_value < 80:
        return "#FFA500"
    elif compaction_value < 85:
        return "#FFD700"
    elif compaction_value < 90:
        return "#FFFF00"
    elif compaction_value < 95:
        return "#ADFF2F"
    elif compaction_value < 100:
        return "#32CD32"
    elif compaction_value < 105:
        return "#228B22"
    elif compaction_value < 110:
        return "#1E90FF"
    else:
        return "#00008B"


def get_status_text(compaction_value: float, target_min: float = 95.0, target_max: float = 100.0) -> tuple:
    """تحديد حالة النقطة"""
    if compaction_value < target_min:
        return "🔴 غير مقبول - يحتاج إعادة دمك", "poor"
    elif compaction_value <= target_max:
        return "🟢 مقبول - مطابق للمواصفات", "good"
    else:
        return "🔵 دمك مفرط - تجاوز الحد المطلوب", "over"

# ----------------------------- الشريط الجانبي -----------------------------
with st.sidebar:
    st.markdown("## 🏗️ FMA نظام الدمك الذكي")
    st.markdown("---")
    
    # نظام GPS
    st.subheader("📍 نظام التتبع اللحظي")
    
    gps_location = streamlit_js_eval(
        js_expressions='''
        new Promise((resolve) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy}),
                    (err) => resolve(null),
                    {enableHighAccuracy: true, timeout: 10000}
                );
            } else {
                resolve(null);
            }
        })
        ''',
        key='gps_tracker',
        debounce=1000
    )
    
    if gps_location and gps_location.get('lat'):
        current_lat = gps_location['lat']
        current_lon = gps_location['lon']
        current_accuracy = gps_location.get('acc', 0)
        st.success(f"📍 GPS نشط | الدقة: {current_accuracy:.0f}m")
    else:
        current_lat = 13.9633333
        current_lon = 44.5819444
        st.warning("⚠️ جاري البحث عن GPS...")
    
    st.markdown("---")
    
    # بيانات المشروع
    with st.expander("📋 بيانات المشروع", expanded=True):
        project_code = st.text_input("رمز المشروع", value=f"FMA-{datetime.now().strftime('%Y%m%d')}")
        project_name = st.text_input("اسم المشروع", value="مشروع طريق إب - تعز")
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1)
    
    # معايرة التربة
    with st.expander("🔧 معايرة التربة", expanded=True):
        ref_lat = st.number_input("خط العرض المرجعي", format="%.8f", value=current_lat)
        ref_lon = st.number_input("خط الطول المرجعي", format="%.8f", value=current_lon)
        
        col1, col2 = st.columns(2)
        with col1:
            initial_compaction = st.number_input("الدمك الابتدائي (%)", value=78.0)
            reference_passes = st.number_input("عدد الدورات المرجعية", value=8)
        with col2:
            final_compaction = st.number_input("الدمك النهائي (%)", value=98.5)
            initial_moisture = st.number_input("الرطوبة الابتدائية (%)", value=11.2)
        
        optimum_moisture = st.number_input("الرطوبة المثلى OMC (%)", value=12.5)
        machine_efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)
        target_min = st.number_input("الحد الأدنى المستهدف (%)", value=95.0)
        target_max = st.number_input("الحد الأقصى المستهدف (%)", value=100.0)
        
        if st.button("✅ تأكيد المعايرة", type="primary", use_container_width=True):
            st.session_state.reference_set = True
            st.session_state.reference_data = {
                "lat": ref_lat, "lon": ref_lon,
                "initial": initial_compaction, "passes": reference_passes,
                "final": final_compaction, "initial_moisture": initial_moisture,
                "omc": optimum_moisture, "efficiency": machine_efficiency,
                "target_min": target_min, "target_max": target_max
            }
            st.success("✅ تم حفظ المعايرة")
            st.rerun()
    
    # إحصائيات سريعة (تم التصحيح هنا)
    st.markdown("---")
    if st.session_state.fma_records:
        df_stats = pd.DataFrame(st.session_state.fma_records)
        # ✅ التصحيح: استخدام 'Compaction_%' بدلاً من 'Compaction'
        st.metric("📊 عدد النقاط", len(df_stats))
        st.metric("📈 متوسط الدمك", f"{df_stats['Compaction_%'].mean():.1f}%")
        if st.session_state.reference_set:
            passed = (df_stats['Compaction_%'] >= st.session_state.reference_data['target_min']).sum()
            st.metric("✅ النقاط المقبولة", f"{passed}/{len(df_stats)}")
    else:
        st.info("لا توجد نقاط مسجلة")

# ----------------------------- الواجهة الرئيسية -----------------------------
st.title("🏗️ FMA نظام الدمك الذكي")
st.markdown("#### *رصد ميداني | خرائط حرارية | تقارير فورية*")

if st.session_state.reference_set:
    st.success(f"✅ المعايرة مكتملة | النقطة المرجعية: {st.session_state.reference_data['lat']:.6f}")
else:
    st.warning("⚠️ يرجى إكمال المعايرة في الشريط الجانبي")

st.markdown("---")

# ==================== التبويبات ====================
tab1, tab2, tab3 = st.tabs(["🚀 الرصد الميداني", "🗺️ الخريطة الحرارية", "📊 التقارير"])

# ==================== TAB 1: الرصد الميداني ====================
with tab1:
    st.subheader("📍 رصد نقاط الدمك")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.info(f"📍 الموقع الحالي: {current_lat:.6f}, {current_lon:.6f}")
        
        current_passes = st.number_input("عدد دورات الدمك", min_value=1, max_value=30, value=8)
        current_moisture = st.number_input("الرطوبة الحالية (%)", min_value=5.0, max_value=25.0, value=12.0)
        point_notes = st.text_area("ملاحظات", placeholder="أي ملاحظات...", height=68)
        
        if st.button("💾 تسجيل النقطة", type="primary", use_container_width=True):
            if not st.session_state.reference_set:
                st.error("❌ يرجى إكمال المعايرة أولاً")
            else:
                ref = st.session_state.reference_data
                
                compaction_value = calculate_compaction_modulus(
                    current_passes, current_moisture,
                    ref['passes'], ref['initial'], ref['final'],
                    ref['omc'], ref['efficiency'], ref['initial']
                )
                
                status_text, status_type = get_status_text(compaction_value, ref['target_min'], ref['target_max'])
                color = get_compaction_color(compaction_value)
                
                new_record = {
                    "ID": len(st.session_state.fma_records) + 1,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Latitude": current_lat,
                    "Longitude": current_lon,
                    "Passes": current_passes,
                    "Moisture_%": current_moisture,
                    "Compaction_%": compaction_value,  # ✅ المفتاح الصحيح
                    "Status": status_text,
                    "Status_Type": status_type,
                    "Color": color,
                    "Notes": point_notes
                }
                
                st.session_state.fma_records.append(new_record)
                st.toast(f"✅ تم تسجيل النقطة #{len(st.session_state.fma_records)} | الدمك: {compaction_value:.1f}%")
                st.balloons()
                time.sleep(0.5)
                st.rerun()
    
    with col2:
        st.markdown("#### آخر النقاط المسجلة")
        if st.session_state.fma_records:
            df_recent = pd.DataFrame(st.session_state.fma_records[-5:])
            # ✅ التصحيح: استخدام 'Compaction_%'
            st.dataframe(
                df_recent[["ID", "Time", "Passes", "Compaction_%", "Status"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("لا توجد نقاط مسجلة")

# ==================== TAB 2: الخريطة الحرارية ====================
with tab2:
    st.subheader("🗺️ الخريطة الحرارية")
    
    if st.session_state.fma_records:
        df = pd.DataFrame(st.session_state.fma_records)
        
        fig = px.scatter_mapbox(
            df,
            lat="Latitude",
            lon="Longitude",
            color="Compaction_%",  # ✅ التصحيح
            size=[15] * len(df),
            size_max=20,
            color_continuous_scale="RdYlGn",
            range_color=[50, 110],
            zoom=16,
            center={"lat": df['Latitude'].mean(), "lon": df['Longitude'].mean()},
            mapbox_style="carto-positron",
            title=f"خريطة الدمك - {len(df)} نقطة",
            hover_data={"ID": True, "Passes": True, "Compaction_%": ":.1f", "Status": True}
        )
        
        # إضافة خط المسار
        fig.add_trace(
            go.Scattermapbox(
                lat=df['Latitude'].tolist(),
                lon=df['Longitude'].tolist(),
                mode='lines+markers',
                marker=dict(size=8, color='gray'),
                line=dict(width=2, color='darkgray'),
                name='مسار المعدة'
            )
        )
        
        # النقطة المرجعية
        if st.session_state.reference_set:
            ref = st.session_state.reference_data
            fig.add_trace(
                go.Scattermapbox(
                    lat=[ref['lat']],
                    lon=[ref['lon']],
                    mode="markers",
                    marker=dict(size=20, symbol="star", color="gold"),
                    name="النقطة المرجعية"
                )
            )
        
        fig.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=550)
        st.plotly_chart(fig, use_container_width=True)
        
        # إحصائيات
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 متوسط الدمك", f"{df['Compaction_%'].mean():.1f}%")
        with col2:
            good = len(df[df['Status_Type'] == 'good'])
            st.metric("✅ مقبول", f"{good}/{len(df)}")
        with col3:
            st.metric("📐 الانحراف", f"{df['Compaction_%'].std():.2f}")
    else:
        st.info("لا توجد نقاط مسجلة")

# ==================== TAB 3: التقارير ====================
with tab3:
    st.subheader("📊 التقارير والتصدير")
    
    if st.session_state.fma_records:
        df = pd.DataFrame(st.session_state.fma_records)
        
        # إحصائيات
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("عدد النقاط", len(df))
        with col2:
            st.metric("أعلى قيمة", f"{df['Compaction_%'].max():.1f}%")
        with col3:
            st.metric("أدنى قيمة", f"{df['Compaction_%'].min():.1f}%")
        with col4:
            st.metric("المتوسط", f"{df['Compaction_%'].mean():.1f}%")
        with col5:
            st.metric("الوسيط", f"{df['Compaction_%'].median():.1f}%")
        
        # رسم بياني للتوزيع
        fig_hist = px.histogram(
            df, x="Compaction_%", nbins=15,
            title="توزيع معامل الدمك",
            labels={"Compaction_%": "معامل الدمك (%)", "count": "عدد النقاط"}
        )
        
        if st.session_state.reference_set:
            ref = st.session_state.reference_data
            fig_hist.add_vline(x=ref['target_min'], line_dash="dash", line_color="green")
            fig_hist.add_vline(x=ref['target_max'], line_dash="dash", line_color="orange")
        
        st.plotly_chart(fig_hist, use_container_width=True)
        
        # تصدير Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Compaction_Data', index=False)
        
        st.download_button(
            label="📥 تحميل تقرير Excel",
            data=output.getvalue(),
            file_name=f"FMA_Report_{project_code}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        # عرض البيانات
        st.dataframe(df[["ID", "Timestamp", "Latitude", "Longitude", "Passes", "Compaction_%", "Status"]], 
                     use_container_width=True)
    else:
        st.info("لا توجد بيانات")

st.markdown("---")
st.caption(f"FMA Compaction System | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
