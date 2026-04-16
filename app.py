"""
================================================================================
FMA COMPACTION ANALYZER PRO - الإصدار المدمج العملي
================================================================================
مميزات النظام المدمج:
✓ رصد ميداني تلقائي باستخدام GPS الفعلي
✓ حساب ديناميكي لمعامل الدمك مع معايرة مرجعية
✓ تسجيل نقاط متعددة مع عدد دورات مختلف لكل نقطة
✓ خريطة حرارية تفاعلية مع تتبع المسار
✓ تقارير Excel مع إحصائيات كاملة
✓ واجهة مستخدم بسيطة وعملية
✓ دعم كامل للغة العربية
================================================================================
"""

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
from streamlit_js_eval import streamlit_js_eval
import time

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction Analyzer Pro - النظام المتكامل",
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
    """
    حساب معامل الدمك بناءً على المعادلات الهندسية
    """
    effective_efficiency = machine_efficiency / 100.0
    
    # حساب الطاقة النسبية (نموذج لوغاريتمي)
    energy_current = math.log1p(current_passes * effective_efficiency)
    energy_reference = math.log1p(reference_passes * effective_efficiency)
    
    if energy_reference <= 0:
        energy_ratio = 1.0
    else:
        energy_ratio = min(energy_current / energy_reference, 1.5)
    
    # تأثير الرطوبة
    moisture_deviation = abs(current_moisture - optimum_moisture)
    moisture_factor = math.exp(-0.06 * moisture_deviation)
    moisture_factor = max(0.7, min(1.0, moisture_factor))
    
    # التحسن الكلي
    total_improvement_reference = reference_compaction_after - reference_compaction_before
    current_improvement = total_improvement_reference * energy_ratio * moisture_factor
    
    # معامل الدمك النهائي
    compaction_modulus = initial_compaction + current_improvement
    return round(min(compaction_modulus, 112.0), 2)


def get_compaction_color(compaction_value: float) -> str:
    """
    تحديد اللون حسب قيمة معامل الدمك (10 تدرجات عملية)
    """
    if compaction_value < 50:
        return "#8B0000"      # أحمر غامق
    elif compaction_value < 60:
        return "#FF0000"      # أحمر
    elif compaction_value < 70:
        return "#FF4500"      # برتقالي محمر
    elif compaction_value < 80:
        return "#FFA500"      # برتقالي
    elif compaction_value < 85:
        return "#FFD700"      # ذهبي
    elif compaction_value < 90:
        return "#FFFF00"      # أصفر
    elif compaction_value < 95:
        return "#ADFF2F"      # أصفر مخضر
    elif compaction_value < 100:
        return "#32CD32"      # أخضر
    elif compaction_value < 105:
        return "#228B22"      # أخضر غامق
    elif compaction_value < 110:
        return "#1E90FF"      # أزرق
    else:
        return "#00008B"      # أزرق غامق (دمك مفرط)


def get_status_text(compaction_value: float, target_min: float = 95.0, target_max: float = 100.0) -> tuple:
    """
    تحديد حالة النقطة ونصها
    """
    if compaction_value < target_min:
        return "🔴 غير مقبول - يحتاج إعادة دمك", "poor"
    elif compaction_value <= target_max:
        return "🟢 مقبول - مطابق للمواصفات", "good"
    else:
        return "🔵 دمك مفرط - تجاوز الحد المطلوب", "over"


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    حساب المسافة بين نقطتين باستخدام Haversine formula
    """
    R = 6371000  # نصف قطر الأرض بالمتر
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

# ----------------------------- الشريط الجانبي -----------------------------
with st.sidebar:
    st.markdown("## 🏗️ FMA نظام الدمك الذكي")
    st.markdown("#### *الإصدار المتكامل العملي*")
    st.markdown("---")
    
    # ========== نظام GPS المباشر ==========
    st.subheader("📍 نظام التتبع اللحظي")
    
    # جلب موقع GPS الفعلي
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
        st.caption(f"الموقع: {current_lat:.6f}, {current_lon:.6f}")
    else:
        current_lat = 13.9633333
        current_lon = 44.5819444
        st.warning("⚠️ جاري البحث عن GPS...")
        st.caption("استخدم الإحداثيات الافتراضية مؤقتاً")
    
    st.markdown("---")
    
    # ========== بيانات المشروع ==========
    with st.expander("📋 بيانات المشروع", expanded=True):
        project_code = st.text_input("رمز المشروع", value=f"FMA-{datetime.now().strftime('%Y%m%d')}")
        project_name = st.text_input("اسم المشروع", value="مشروع طريق إب - تعز")
        project_location = st.text_input("الموقع", value="محافظة إب - اليمن")
        engineer_name = st.text_input("اسم المهندس", value="د. أحمد العرامي")
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1, step=1)
    
    # ========== معاملات المعايرة ==========
    with st.expander("🔧 معايرة التربة (مرجعية)", expanded=True):
        st.info("أدخل قيم النقطة المرجعية بعد الدمك")
        
        ref_lat = st.number_input("خط العرض المرجعي", format="%.8f", value=current_lat)
        ref_lon = st.number_input("خط الطول المرجعي", format="%.8f", value=current_lon)
        
        if st.button("📍 استخدام الموقع الحالي كمرجع", use_container_width=True):
            if gps_location and gps_location.get('lat'):
                ref_lat = gps_location['lat']
                ref_lon = gps_location['lon']
                st.success("تم تحديث الإحداثيات المرجعية")
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1:
            initial_compaction = st.number_input("معامل الدمك الابتدائي (%)", min_value=50.0, max_value=90.0, value=78.0)
            reference_passes = st.number_input("عدد دورات الدمك المرجعية", min_value=1, max_value=30, value=8)
        with col2:
            final_compaction = st.number_input("معامل الدمك النهائي (%)", min_value=80.0, max_value=112.0, value=98.5)
            initial_moisture = st.number_input("الرطوبة الابتدائية (%)", min_value=5.0, max_value=25.0, value=11.2)
        
        optimum_moisture = st.number_input("الرطوبة المثلى OMC (%)", min_value=5.0, max_value=30.0, value=12.5)
        machine_efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100, help="100% = معدة جديدة")
        
        target_min = st.number_input("الحد الأدنى المستهدف (%)", min_value=80.0, max_value=100.0, value=95.0)
        target_max = st.number_input("الحد الأقصى المستهدف (%)", min_value=95.0, max_value=115.0, value=100.0)
        
        if st.button("✅ تأكيد المعايرة", type="primary", use_container_width=True):
            st.session_state.reference_set = True
            st.session_state.reference_data = {
                "lat": ref_lat, "lon": ref_lon,
                "initial": initial_compaction, "passes": reference_passes,
                "final": final_compaction, "initial_moisture": initial_moisture,
                "omc": optimum_moisture, "efficiency": machine_efficiency,
                "target_min": target_min, "target_max": target_max
            }
            st.success("✅ تم حفظ المعايرة بنجاح")
            st.rerun()
    
    # ========== إحصائيات سريعة ==========
    st.markdown("---")
    if st.session_state.fma_records:
        df_stats = pd.DataFrame(st.session_state.fma_records)
        st.metric("📊 عدد النقاط المسجلة", len(df_stats))
        st.metric("📈 متوسط معامل الدمك", f"{df_stats['Compaction'].mean():.1f}%")
        if st.session_state.reference_set:
            passed = (df_stats['Compaction'] >= st.session_state.reference_data['target_min']).sum()
            st.metric("✅ النقاط المقبولة", f"{passed}/{len(df_stats)}")
    else:
        st.info("لا توجد نقاط مسجلة بعد")

# ----------------------------- الواجهة الرئيسية -----------------------------
st.title("🏗️ FMA نظام الدمك الذكي المتكامل")
st.markdown("#### *رصد ميداني تلقائي | خرائط حرارية | تقارير فورية*")

# عرض حالة المعايرة
if st.session_state.reference_set:
    st.success(f"✅ المعايرة مكتملة | النقطة المرجعية: {st.session_state.reference_data['lat']:.6f}, {st.session_state.reference_data['lon']:.6f}")
else:
    st.warning("⚠️ يرجى إكمال المعايرة في الشريط الجانبي قبل بدء الرصد")

st.markdown("---")

# ==================== التبويبات الرئيسية ====================
tab1, tab2, tab3 = st.tabs(["🚀 الرصد الميداني", "🗺️ الخريطة الحرارية", "📊 التقارير والتحليل"])

# ==================== TAB 1: الرصد الميداني ====================
with tab1:
    st.subheader("📍 رصد نقاط الدمك الميداني")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("#### 📝 إدخال بيانات النقطة")
        
        # عرض الموقع الحالي
        st.info(f"📍 الموقع الحالي: {current_lat:.6f}, {current_lon:.6f}")
        
        # إدخال عدد الدورات والرطوبة
        current_passes = st.number_input("عدد دورات الدمك لهذه النقطة", min_value=1, max_value=30, value=8, step=1)
        current_moisture = st.number_input("المحتوى الرطوبي الحالي (%)", min_value=5.0, max_value=25.0, value=12.0, step=0.5)
        
        # ملاحظات إضافية
        point_notes = st.text_area("ملاحظات (اختياري)", placeholder="أي ملاحظات عن هذه النقطة...", height=68)
        
        # زر التسجيل
        if st.button("💾 تسجيل النقطة وحساب معامل الدمك", type="primary", use_container_width=True):
            if not st.session_state.reference_set:
                st.error("❌ يرجى إكمال المعايرة أولاً")
            else:
                ref = st.session_state.reference_data
                
                # حساب معامل الدمك
                compaction_value = calculate_compaction_modulus(
                    current_passes=current_passes,
                    current_moisture=current_moisture,
                    reference_passes=ref['passes'],
                    reference_compaction_before=ref['initial'],
                    reference_compaction_after=ref['final'],
                    optimum_moisture=ref['omc'],
                    machine_efficiency=ref['efficiency'],
                    initial_compaction=ref['initial']
                )
                
                # تحديد الحالة واللون
                status_text, status_type = get_status_text(compaction_value, ref['target_min'], ref['target_max'])
                color = get_compaction_color(compaction_value)
                
                # إنشاء سجل جديد
                new_record = {
                    "ID": len(st.session_state.fma_records) + 1,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Latitude": current_lat,
                    "Longitude": current_lon,
                    "Passes": current_passes,
                    "Moisture_%": current_moisture,
                    "Compaction_%": compaction_value,
                    "Status": status_text,
                    "Status_Type": status_type,
                    "Color": color,
                    "Notes": point_notes
                }
                
                st.session_state.fma_records.append(new_record)
                st.toast(f"✅ تم تسجيل النقطة #{len(st.session_state.fma_records)} | معامل الدمك: {compaction_value:.1f}%", icon="✅")
                st.balloons()
                time.sleep(0.5)
                st.rerun()
    
    with col2:
        st.markdown("#### 📋 آخر النقاط المسجلة")
        
        if st.session_state.fma_records:
            df_recent = pd.DataFrame(st.session_state.fma_records[-5:])
            st.dataframe(
                df_recent[["ID", "Time", "Passes", "Compaction_%", "Status"]],
                use_container_width=True,
                hide_index=True
            )
            
            # عرض إحصائيات سريعة للنقاط المسجلة
            df_all = pd.DataFrame(st.session_state.fma_records)
            st.markdown("#### 📊 ملخص سريع")
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("مجموع النقاط", len(df_all))
            with col_b:
                st.metric("متوسط الدمك", f"{df_all['Compaction_%'].mean():.1f}%")
            with col_c:
                if st.session_state.reference_set:
                    good_count = len(df_all[df_all['Compaction_%'] >= st.session_state.reference_data['target_min']])
                    st.metric("النقاط المقبولة", f"{good_count}/{len(df_all)}")
        else:
            st.info("💡 لا توجد نقاط مسجلة بعد. قم بتسجيل أول نقطة")

# ==================== TAB 2: الخريطة الحرارية ====================
with tab2:
    st.subheader("🗺️ الخريطة الحرارية لجودة الدمك")
    
    if st.session_state.fma_records:
        df = pd.DataFrame(st.session_state.fma_records)
        
        # خريطة تفاعلية
        fig = px.scatter_mapbox(
            df,
            lat="Latitude",
            lon="Longitude",
            color="Compaction_%",
            size=[15] * len(df),
            size_max=20,
            color_continuous_scale=[
                (0.00, "#8B0000"), (0.10, "#FF0000"), (0.20, "#FF4500"),
                (0.30, "#FFA500"), (0.40, "#FFD700"), (0.50, "#FFFF00"),
                (0.60, "#ADFF2F"), (0.70, "#32CD32"), (0.80, "#228B22"),
                (0.90, "#1E90FF"), (1.00, "#00008B")
            ],
            range_color=[50, 110],
            zoom=16,
            center={"lat": df['Latitude'].mean(), "lon": df['Longitude'].mean()},
            mapbox_style="carto-positron",
            title=f"مسار المعدة - {len(df)} نقطة مسجلة | مشروع: {project_code}",
            hover_data={
                "ID": True, "Passes": True, "Moisture_%": True, 
                "Compaction_%": ":.1f", "Status": True, "Timestamp": True
            }
        )
        
        # إضافة خط يوضح مسار المعدة
        fig.add_trace(
            go.Scattermapbox(
                lat=df['Latitude'].tolist(),
                lon=df['Longitude'].tolist(),
                mode='lines+markers',
                marker=dict(size=8, color='gray', symbol='circle'),
                line=dict(width=2, color='darkgray', dash='solid'),
                name='📍 مسار المعدة',
                showlegend=True,
                hovertemplate='مسار المعدة<br>Lat: %{lat:.6f}<br>Lon: %{lon:.6f}<extra></extra>'
            )
        )
        
        # إضافة النقطة المرجعية إن وجدت
        if st.session_state.reference_set:
            ref = st.session_state.reference_data
            fig.add_trace(
                go.Scattermapbox(
                    lat=[ref['lat']],
                    lon=[ref['lon']],
                    mode="markers",
                    marker=dict(size=20, symbol="star", color="gold"),
                    name="⭐ النقطة المرجعية",
                    showlegend=True,
                    hoverinfo="text",
                    text=f"Reference Point<br>Initial: {ref['initial']}%<br>Final: {ref['final']}%<br>Passes: {ref['passes']}"
                )
            )
        
        # إضافة سهم اتجاه الشمال
        fig.add_annotation(
            x=0.02, y=0.98,
            xref="paper", yref="paper",
            text="↑ N",
            showarrow=False,
            font=dict(size=20, color="black", family="Arial Black"),
            bgcolor="rgba(255,255,255,0.7)",
            bordercolor="black",
            borderwidth=1
        )
        
        fig.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            height=600,
            coloraxis_colorbar=dict(
                title="معامل الدمك (%)",
                tickvals=[50, 60, 70, 80, 85, 90, 95, 100, 105, 110],
                ticktext=["<50", "50-60", "60-70", "70-80", "80-85", "85-90", "90-95", "95-100", "100-105", "105-110"]
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # إحصائيات إضافية
        st.markdown("---")
        st.subheader("📊 توزيع جودة الدمك")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            good = len(df[df['Status_Type'] == 'good'])
            st.metric("✅ مقبول", good, delta=f"{good/len(df)*100:.0f}%")
        with col2:
            poor = len(df[df['Status_Type'] == 'poor'])
            st.metric("❌ غير مقبول", poor, delta=f"{poor/len(df)*100:.0f}%")
        with col3:
            over = len(df[df['Status_Type'] == 'over'])
            st.metric("⚠️ دمك مفرط", over, delta=f"{over/len(df)*100:.0f}%")
        with col4:
            st.metric("📊 الانحراف المعياري", f"{df['Compaction_%'].std():.2f}")
        
    else:
        st.info("💡 لا توجد نقاط مسجلة لعرض الخريطة. قم بتسجيل نقاط في تبويب الرصد الميداني")

# ==================== TAB 3: التقارير والتحليل ====================
with tab3:
    st.subheader("📊 التقارير والتحليل الإحصائي")
    
    if st.session_state.fma_records:
        df = pd.DataFrame(st.session_state.fma_records)
        
        # إحصائيات تفصيلية
        st.markdown("#### 📈 إحصائيات تفصيلية")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📊 عدد النقاط", len(df))
        with col2:
            st.metric("📈 أعلى قيمة", f"{df['Compaction_%'].max():.1f}%")
        with col3:
            st.metric("📉 أدنى قيمة", f"{df['Compaction_%'].min():.1f}%")
        with col4:
            st.metric("📐 المتوسط", f"{df['Compaction_%'].mean():.1f}%")
        with col5:
            st.metric("📏 الوسيط", f"{df['Compaction_%'].median():.1f}%")
        
        # رسم بياني للتوزيع
        st.markdown("#### 📊 توزيع قيم معامل الدمك")
        
        fig_hist = px.histogram(
            df, 
            x="Compaction_%", 
            nbins=15,
            title="توزيع معامل الدمك عبر النقاط المسجلة",
            labels={"Compaction_%": "معامل الدمك (%)", "count": "عدد النقاط"},
            color_discrete_sequence=["#2c3e50"]
        )
        
        # إضافة خطوط الأهداف
        if st.session_state.reference_set:
            ref = st.session_state.reference_data
            fig_hist.add_vline(
                x=ref['target_min'], 
                line_dash="dash", 
                line_color="green", 
                annotation_text=f"الهدف الأدنى {ref['target_min']}%",
                annotation_position="top"
            )
            fig_hist.add_vline(
                x=ref['target_max'], 
                line_dash="dash", 
                line_color="orange", 
                annotation_text=f"الهدف الأعلى {ref['target_max']}%",
                annotation_position="top"
            )
        
        st.plotly_chart(fig_hist, use_container_width=True)
        
        # العلاقة بين عدد الدورات ومعامل الدمك
        st.markdown("#### 🔄 العلاقة بين عدد الدورات ومعامل الدمك")
        
        fig_scatter = px.scatter(
            df,
            x="Passes",
            y="Compaction_%",
            color="Compaction_%",
            color_continuous_scale="RdYlGn",
            title="تأثير عدد الدورات على معامل الدمك",
            labels={"Passes": "عدد الدورات", "Compaction_%": "معامل الدمك (%)"},
            trendline="lowess",
            trendline_color_override="blue"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        # جدول جميع البيانات
        st.markdown("#### 📋 جميع النقاط المسجلة")
        st.dataframe(
            df[["ID", "Timestamp", "Latitude", "Longitude", "Passes", "Moisture_%", "Compaction_%", "Status"]],
            use_container_width=True,
            height=300
        )
        
        # ========== أزرار التصدير ==========
        st.markdown("---")
        st.subheader("📥 تصدير التقارير")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # تصدير Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Compaction_Data', index=False)
                
                # إضافة ملخص
                if st.session_state.reference_set:
                    ref = st.session_state.reference_data
                    summary_data = {
                        "Parameter": ["Project Code", "Project Name", "Location", "Engineer", "Layer Number",
                                      "Reference Point", "Initial Compaction", "Reference Passes", "Final Compaction",
                                      "Optimum Moisture", "Machine Efficiency", "Target Min", "Target Max",
                                      "Date", "Total Points", "Average Compaction", "Min Compaction", "Max Compaction",
                                      "Points Passed", "Points Failed", "Points Over-compacted"],
                        "Value": [project_code, project_name, project_location, engineer_name, layer_number,
                                  f"{ref['lat']:.6f}, {ref['lon']:.6f}", f"{ref['initial']}%", ref['passes'], f"{ref['final']}%",
                                  f"{ref['omc']}%", f"{ref['efficiency']}%", f"{ref['target_min']}%", f"{ref['target_max']}%",
                                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(df),
                                  f"{df['Compaction_%'].mean():.1f}%", f"{df['Compaction_%'].min():.1f}%", f"{df['Compaction_%'].max():.1f}%",
                                  len(df[df['Status_Type'] == 'good']), len(df[df['Status_Type'] == 'poor']), len(df[df['Status_Type'] == 'over'])]
                    }
                    pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            st.download_button(
                label="📊 تحميل تقرير Excel",
                data=output.getvalue(),
                file_name=f"FMA_Report_{project_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col2:
            # تصدير CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 تحميل CSV",
                data=csv,
                file_name=f"FMA_Data_{project_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col3:
            # تصدير الخريطة كـ HTML
            fig_map = px.scatter_mapbox(
                df, lat="Latitude", lon="Longitude", color="Compaction_%",
                zoom=16, mapbox_style="carto-positron",
                title=f"FMA Map - {project_code}"
            )
            fig_map.write_html(f"FMA_Map_{project_code}.html")
            with open(f"FMA_Map_{project_code}.html", "r", encoding='utf-8') as f:
                st.download_button(
                    label="🗺️ تحميل الخريطة (HTML)",
                    data=f.read(),
                    file_name=f"FMA_Map_{project_code}.html",
                    mime="text/html",
                    use_container_width=True
                )
        
        # زر مسح جميع البيانات
        st.markdown("---")
        if st.button("🗑️ مسح جميع البيانات", type="secondary", use_container_width=True):
            st.session_state.fma_records = []
            st.success("✅ تم مسح جميع البيانات بنجاح")
            st.rerun()
            
    else:
        st.info("💡 لا توجد بيانات لعرضها. قم بتسجيل نقاط في تبويب الرصد الميداني")

# ==================== تذييل الصفحة ====================
st.markdown("---")
st.caption(f"""
🏗️ **FMA Compaction Analyzer Pro v3.0** | نظام الدمك الذكي المتكامل  
📅 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | © 2026 جميع الحقوق محفوظة
""")

print("✅ FMA Compaction System is running successfully!")
