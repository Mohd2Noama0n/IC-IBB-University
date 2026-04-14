"""
FMA Compaction Analyzer Pro - الإصدار المتكامل
تسجيل تلقائي للنقاط + نظام وحدات متري/إمبراطوري
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import math
import sqlite3
import json
import warnings
from streamlit_js_eval import streamlit_js_eval
import threading
import time

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction Tracker - تسجيل تلقائي",
    page_icon="📍",
    layout="wide"
)

# ----------------------------- دوال تحويل الوحدات -----------------------------
class UnitConverter:
    """تحويل الوحدات بين المتري والإمبراطوري"""
    
    def __init__(self, system="metric"):
        self.system = system  # metric أو imperial
    
    def format_distance(self, meters):
        """تنسيق المسافة حسب النظام المختار"""
        if self.system == "metric":
            if meters >= 1000:
                return f"{meters/1000:.2f} km"
            return f"{meters:.1f} m"
        else:
            feet = meters * 3.28084
            if feet >= 5280:
                return f"{feet/5280:.2f} mi"
            return f"{feet:.1f} ft"
    
    def format_speed(self, meters_per_sec):
        """تنسيق السرعة حسب النظام المختار"""
        if self.system == "metric":
            kmh = meters_per_sec * 3.6
            return f"{kmh:.1f} km/h"
        else:
            mph = meters_per_sec * 2.23694
            return f"{mph:.1f} mph"
    
    def format_area(self, sq_meters):
        """تنسيق المساحة حسب النظام المختار"""
        if self.system == "metric":
            return f"{sq_meters:.1f} m²"
        else:
            sq_feet = sq_meters * 10.7639
            return f"{sq_feet:.1f} ft²"
    
    def density_display(self, value_kg_m3):
        """عرض الكثافة حسب النظام"""
        if self.system == "metric":
            return f"{value_kg_m3:.0f} kg/m³"
        else:
            pcf = value_kg_m3 * 0.06242796
            return f"{pcf:.1f} pcf"
    
    def get_spacing_threshold(self, user_value, is_meters=True):
        """تحويل قيمة التباعد من وحدة المستخدم إلى متر للتخزين"""
        if self.system == "metric":
            return user_value  # المستخدم أدخل بالمتر
        else:
            # المستخدم أدخل بالقدم، نحول إلى متر
            return user_value * 0.3048
    
    def display_spacing_threshold(self, meters):
        """عرض قيمة التباعد للمستخدم بوحدته المفضلة"""
        if self.system == "metric":
            return meters
        else:
            return meters * 3.28084


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
    """حساب معامل الدمك بناءً على المعايرة"""
    
    effective_efficiency = machine_efficiency / 100.0
    
    # حساب الطاقة النسبية
    energy_current = math.log1p(current_passes * effective_efficiency)
    energy_reference = math.log1p(reference_passes * effective_efficiency)
    
    if energy_reference <= 0:
        energy_ratio = 1.0
    else:
        energy_ratio = min(energy_current / energy_reference, 1.5)
    
    # تأثير الرطوبة
    moisture_deviation = abs(current_moisture - optimum_moisture)
    moisture_factor = math.exp(-0.06 * moisture_deviation)
    moisture_factor = max(0.65, min(1.0, moisture_factor))
    
    # التحسن الكلي
    total_improvement_reference = reference_compaction_after - reference_compaction_before
    current_improvement = total_improvement_reference * energy_ratio * moisture_factor
    
    compaction_modulus = initial_compaction + current_improvement
    return round(min(compaction_modulus, 112.0), 2)


def get_heatmap_color(compaction_value: float) -> str:
    """تحديد اللون حسب قيمة الدمك (15 تدرج)"""
    if compaction_value < 40:
        return "#8B0000"
    elif compaction_value < 50:
        return "#B22222"
    elif compaction_value < 60:
        return "#DC143C"
    elif compaction_value < 65:
        return "#FF4500"
    elif compaction_value < 70:
        return "#FF6347"
    elif compaction_value < 75:
        return "#FF8C00"
    elif compaction_value < 80:
        return "#FFA500"
    elif compaction_value < 85:
        return "#FFD700"
    elif compaction_value < 88:
        return "#FFFF00"
    elif compaction_value < 91:
        return "#ADFF2F"
    elif compaction_value < 94:
        return "#7CFC00"
    elif compaction_value < 97:
        return "#32CD32"
    elif compaction_value < 100:
        return "#228B22"
    elif compaction_value < 105:
        return "#1E90FF"
    elif compaction_value < 110:
        return "#191970"
    else:
        return "#4B0082"


def calculate_distance(lat1, lon1, lat2, lon2):
    """حساب المسافة بين نقطتين بالأمتار (Haversine formula)"""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

# ----------------------------- واجهة المستخدم -----------------------------
# تهيئة حالة الجلسة
if 'tracking_points' not in st.session_state:
    st.session_state.tracking_points = []
    st.session_state.is_tracking = False
    st.session_state.last_position = None
    st.session_state.passes_count = {}
    st.session_state.reference_data = None
    st.session_state.project_data = None
    st.session_state.auto_tracking = False
    st.session_state.last_gps_update = None
    st.session_state.unit_converter = UnitConverter("metric")

# الشريط الجانبي
with st.sidebar:
    st.markdown("## 📍 FMA الدمك الذكي")
    st.markdown("---")
    
    # ========== نظام الوحدات ==========
    with st.expander("📏 نظام الوحدات", expanded=True):
        unit_system = st.selectbox(
            "نظام القياس",
            ["metric", "imperial"],
            format_func=lambda x: "متري (متر، كجم)" if x == "metric" else "إمبراطوري (قدم، رطل)",
            help="اختر نظام الوحدات المناسب لمشروعك"
        )
        
        # تحديث محول الوحدات
        if unit_system != st.session_state.unit_converter.system:
            st.session_state.unit_converter = UnitConverter(unit_system)
        
        st.caption(f"✅ النظام الحالي: {'متري' if unit_system == 'metric' else 'إمبراطوري'}")
    
    # ========== بيانات المشروع ==========
    with st.expander("📋 بيانات المشروع", expanded=True):
        project_code = st.text_input("رمز المشروع", value=f"FMA-{datetime.now().strftime('%Y%m%d')}")
        project_name = st.text_input("اسم المشروع", value="مشروع طريق")
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1)
        
        # كثافة معملية مع تحويل الوحدات
        max_density_input = st.number_input(
            f"أقصى كثافة معملية ({'kg/m³' if unit_system == 'metric' else 'pcf'})",
            min_value=1000.0 if unit_system == 'metric' else 62.4,
            value=2100.0 if unit_system == 'metric' else 131.0,
            step=10.0 if unit_system == 'metric' else 1.0
        )
    
    # ========== المعايرة ==========
    with st.expander("🔧 المعايرة المرجعية", expanded=True):
        st.info("📍 قف في موقع معروف واضغط 'تعيين النقطة المرجعية'")
        
        ref_latitude = st.number_input("خط العرض المرجعي", format="%.8f", value=13.9633333)
        ref_longitude = st.number_input("خط الطول المرجعي", format="%.8f", value=44.5819444)
        
        initial_compaction = st.number_input("معامل الدمك الابتدائي (%)", min_value=50.0, max_value=90.0, value=78.0)
        reference_passes = st.number_input("عدد دورات الدمك المرجعية", min_value=1, max_value=30, value=8)
        final_compaction = st.number_input("معامل الدمك النهائي (%)", min_value=80.0, max_value=112.0, value=98.5)
        initial_moisture = st.number_input("الرطوبة الابتدائية (%)", min_value=5.0, max_value=25.0, value=11.2)
        optimum_moisture = st.number_input("الرطوبة المثلى OMC (%)", min_value=5.0, max_value=30.0, value=12.5)
        machine_efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100, help="100% = معدة جديدة")
    
    # ========== إعدادات التتبع التلقائي ==========
    with st.expander("⚙️ إعدادات التتبع التلقائي", expanded=True):
        # مسافة التباعد مع تحويل الوحدات
        spacing_display = st.number_input(
            f"مسافة التباعد للتسجيل ({'متر' if unit_system == 'metric' else 'قدم'})",
            min_value=1.0 if unit_system == 'metric' else 3.0,
            max_value=50.0 if unit_system == 'metric' else 160.0,
            value=5.0 if unit_system == 'metric' else 16.0,
            step=0.5 if unit_system == 'metric' else 1.0,
            help="كلما تحركت هذه المسافة، يتم تسجيل نقطة جديدة تلقائياً"
        )
        
        # تحويل إلى متر للتخزين الداخلي
        spacing_threshold = st.session_state.unit_converter.get_spacing_threshold(spacing_display)
        
        auto_record_interval = st.slider(
            "فترة التحديث التلقائي (ثانية)",
            min_value=0.5, max_value=5.0, value=1.0, step=0.5,
            help="كل كم ثانية يتم محاولة تحديث الموقع"
        )
        
        min_accuracy = st.slider(
            "دقة GPS المطلوبة (متر)",
            min_value=5, max_value=50, value=15,
            help="النقاط ذات دقة أقل من هذه القيمة سيتم تجاهلها"
        )
        
        st.info(f"📡 سيتم تسجيل نقطة تلقائياً كل {st.session_state.unit_converter.format_distance(spacing_threshold)}")

# ==================== الواجهة الرئيسية ====================
st.title("📍 FMA نظام الدمك الذكي - تسجيل تلقائي")
st.markdown(f"#### *حرك هاتفك مع المعدة - يتم التسجيل تلقائياً | النظام: {'متري' if unit_system == 'metric' else 'إمبراطوري'}*")

# ==================== أزرار التحكم الرئيسية ====================
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("📍 تعيين المرجعية", type="primary", use_container_width=True):
        # طلب موقع GPS الحالي
        current_location = streamlit_js_eval(
            js_expressions='''
            new Promise((resolve) => {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(
                        (pos) => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy}),
                        (err) => resolve(null)
                    );
                } else {
                    resolve(null);
                }
            })
            ''',
            key=f'ref_loc_{datetime.now().timestamp()}'
        )
        
        if current_location and current_location.get('lat'):
            st.session_state.reference_data = {
                "lat": current_location['lat'], "lon": current_location['lon'],
                "initial": initial_compaction, "passes": reference_passes,
                "final": final_compaction, "initial_moisture": initial_moisture,
                "omc": optimum_moisture, "efficiency": machine_efficiency,
                "accuracy": current_location.get('acc', 0)
            }
            
            st.session_state.project_data = {
                "code": project_code, "name": project_name, "layer": layer_number,
                "unit_system": unit_system, "max_density": max_density_input
            }
            
            st.success(f"✅ تم تعيين النقطة المرجعية: {current_location['lat']:.6f}, {current_location['lon']:.6f}")
            st.rerun()
        else:
            st.error("❌ يرجى السماح للتطبيق بالوصول إلى GPS")

with col2:
    if st.button("▶️ بدء التتبع", use_container_width=True):
        st.session_state.is_tracking = True
        st.session_state.auto_tracking = True
        st.session_state.tracking_points = []
        st.session_state.passes_count = {}
        st.session_state.last_position = None
        st.success("✅ بدء التتبع التلقائي - حرك الهاتف مع المعدة")
        st.rerun()

with col3:
    if st.button("⏹️ إيقاف التتبع", use_container_width=True):
        st.session_state.is_tracking = False
        st.session_state.auto_tracking = False
        st.warning("⏸️ تم إيقاف التتبع")
        st.rerun()

with col4:
    if st.button("🗑️ مسح الكل", use_container_width=True):
        st.session_state.tracking_points = []
        st.session_state.passes_count = {}
        st.session_state.is_tracking = False
        st.session_state.auto_tracking = False
        st.success("🗑️ تم مسح جميع النقاط")
        st.rerun()

with col5:
    if st.session_state.reference_data:
        st.metric("🎯 المعايرة", "✓ مكتملة", delta=None)
    else:
        st.metric("🎯 المعايرة", "✗ غير مكتملة", delta=None)

st.markdown("---")

# ==================== حالة التتبع وعرض GPS ====================
if st.session_state.is_tracking:
    # عرض حالة التتبع
    st.info(f"📍 **جاري التتبع التلقائي...** سيتم تسجيل نقطة كل {st.session_state.unit_converter.format_distance(spacing_threshold)}")
    
    # JavaScript للحصول على GPS بشكل مستمر
    gps_js = f'''
    let lastLat = null;
    let lastLon = null;
    let lastTime = 0;
    
    function getLocation() {{
        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition(
                (pos) => {{
                    const data = {{
                        lat: pos.coords.latitude,
                        lon: pos.coords.longitude,
                        acc: pos.coords.accuracy,
                        timestamp: Date.now()
                    }};
                    window.parent.postMessage({{type: "streamlit:setComponentValue", value: data}}, "*");
                }},
                (err) => console.log("GPS error:", err),
                {{ enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }}
            );
        }}
    }}
    
    getLocation();
    setInterval(getLocation, {int(auto_record_interval * 1000)});
    '''
    
    # الحصول على موقع GPS الحالي
    current_gps = streamlit_js_eval(
        js_expressions=gps_js,
        key=f'gps_tracking_{datetime.now().timestamp()}',
        debounce=auto_record_interval
    )
    
    if current_gps and isinstance(current_gps, dict) and current_gps.get('lat'):
        current_lat = current_gps['lat']
        current_lon = current_gps['lon']
        current_accuracy = current_gps.get('acc', 0)
        
        # عرض معلومات GPS الحالية
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📍 خط العرض", f"{current_lat:.6f}")
        with col2:
            st.metric("📍 خط الطول", f"{current_lon:.6f}")
        with col3:
            st.metric("🎯 دقة GPS", f"{current_accuracy:.1f} متر")
        with col4:
            points = len(st.session_state.tracking_points)
            st.metric("📊 النقاط المسجلة", points)
        
        # التحقق من دقة GPS
        if current_accuracy <= min_accuracy:
            # التحقق من المسافة عن آخر نقطة مسجلة
            should_record = False
            
            if st.session_state.last_position is None:
                should_record = True
            else:
                distance = calculate_distance(
                    st.session_state.last_position[0], st.session_state.last_position[1],
                    current_lat, current_lon
                )
                
                if distance >= spacing_threshold:
                    should_record = True
                    st.info(f"📏 تم قطع مسافة {st.session_state.unit_converter.format_distance(distance)} - جاري التسجيل...")
            
            if should_record:
                # تحديث عدد مرات المرور لهذه النقطة
                point_key = f"{round(current_lat, 5)}_{round(current_lon, 5)}"
                current_passes = st.session_state.passes_count.get(point_key, 0) + 1
                st.session_state.passes_count[point_key] = current_passes
                
                # حساب معامل الدمك
                if st.session_state.reference_data:
                    ref = st.session_state.reference_data
                    comp_value = calculate_compaction_modulus(
                        current_passes=current_passes,
                        current_moisture=ref['initial_moisture'],
                        reference_passes=ref['passes'],
                        reference_compaction_before=ref['initial'],
                        reference_compaction_after=ref['final'],
                        optimum_moisture=ref['omc'],
                        machine_efficiency=ref['efficiency'],
                        initial_compaction=ref['initial']
                    )
                else:
                    comp_value = 85.0
                
                # إضافة النقطة
                new_point = {
                    "Point_ID": f"P{len(st.session_state.tracking_points)+1}",
                    "Latitude": current_lat,
                    "Longitude": current_lon,
                    "Passes": current_passes,
                    "Compaction_Modulus_%": comp_value,
                    "Color": get_heatmap_color(comp_value),
                    "Accuracy_m": round(current_accuracy, 1),
                    "Timestamp": datetime.now().strftime("%H:%M:%S")
                }
                
                st.session_state.tracking_points.append(new_point)
                st.session_state.last_position = (current_lat, current_lon)
                st.success(f"✅ تم تسجيل النقطة {len(st.session_state.tracking_points)} تلقائياً (معامل الدمك: {comp_value:.1f}%)")
                time.sleep(0.5)
                st.rerun()
        else:
            st.warning(f"⚠️ دقة GPS منخفضة ({current_accuracy:.0f}م > {min_accuracy}م). انتظر حتى تتحسن الإشارة.")
    
    else:
        st.warning("⏳ في انتظار إشارة GPS... يرجى التأكد من تشغيل الموقع في هاتفك")
        st.info("💡 نصيحة: اخرج إلى مكان مفتوح للحصول على إشارة GPS أفضل")

# ==================== عرض النقاط المسجلة ====================
if st.session_state.tracking_points:
    df = pd.DataFrame(st.session_state.tracking_points)
    
    st.subheader(f"📍 النقاط المسجلة تلقائياً ({len(df)} نقطة)")
    
    # عرض الجدول مع وحدات محولة
    display_df = df[["Point_ID", "Latitude", "Longitude", "Passes", "Compaction_Modulus_%", "Accuracy_m", "Timestamp"]].copy()
    st.dataframe(display_df, use_container_width=True, height=200)
    
    # ==================== الخريطة الحرارية ====================
    st.subheader("🗺️ الخريطة الحرارية - مسار المعدة الفعلي")
    
    fig = px.scatter_mapbox(
        df,
        lat="Latitude",
        lon="Longitude",
        color="Compaction_Modulus_%",
        size=[15] * len(df),
        size_max=25,
        color_continuous_scale=[
            (0.00, "#8B0000"), (0.10, "#DC143C"), (0.20, "#FF4500"),
            (0.30, "#FF8C00"), (0.40, "#FFD700"), (0.50, "#FFFF00"),
            (0.60, "#ADFF2F"), (0.70, "#7CFC00"), (0.75, "#32CD32"),
            (0.80, "#228B22"), (0.85, "#1E90FF"), (0.90, "#191970"),
            (1.00, "#4B0082")
        ],
        range_color=[60, 110],
        zoom=17,
        center={"lat": df['Latitude'].mean(), "lon": df['Longitude'].mean()},
        mapbox_style="carto-positron",
        title=f"مسار المعدة - {len(df)} نقطة مسجلة تلقائياً | {st.session_state.unit_converter.format_area(1000)}",
        hover_data={"Point_ID": True, "Passes": True, "Compaction_Modulus_%": ":.1f", "Accuracy_m": True}
    )
    
    # إضافة خط المسار
    fig.add_trace(
        go.Scattermapbox(
            lat=df['Latitude'].tolist(),
            lon=df['Longitude'].tolist(),
            mode='lines+markers',
            marker=dict(size=8, color='gray'),
            line=dict(width=2, color='darkgray', dash='solid'),
            name='📍 مسار المعدة',
            showlegend=True
        )
    )
    
    # إضافة النقطة المرجعية
    if st.session_state.reference_data:
        ref = st.session_state.reference_data
        fig.add_trace(
            go.Scattermapbox(
                lat=[ref['lat']],
                lon=[ref['lon']],
                mode="markers",
                marker=dict(size=20, symbol="star", color="gold"),
                name="⭐ النقطة المرجعية",
                hoverinfo="text",
                text=f"Reference Point<br>Initial: {ref['initial']}%<br>Final: {ref['final']}%<br>Passes: {ref['passes']}"
            )
        )
    
    fig.update_layout(
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
        height=550,
        coloraxis_colorbar=dict(
            title="معامل الدمك (%)",
            tickvals=[60, 70, 80, 85, 90, 95, 100, 105, 110],
            ticktext=["60", "70", "80", "85", "90", "95", "100", "105", "110+"]
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ==================== إحصائيات سريعة ====================
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📊 متوسط الدمك", f"{df['Compaction_Modulus_%'].mean():.1f}%")
    with col2:
        st.metric("📈 أعلى قيمة", f"{df['Compaction_Modulus_%'].max():.1f}%")
    with col3:
        st.metric("📉 أدنى قيمة", f"{df['Compaction_Modulus_%'].min():.1f}%")
    with col4:
        std_val = df['Compaction_Modulus_%'].std()
        st.metric("📐 الانحراف المعياري", f"{std_val:.1f}")
    with col5:
        good_pct = (df['Compaction_Modulus_%'] >= 95).sum() / len(df) * 100
        st.metric("✅ نسبة الجيد", f"{good_pct:.0f}%")
    
    # ==================== زر التصدير ====================
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 تصدير إلى Excel", use_container_width=True):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Compaction_Data', index=False)
                
                # إضافة ملخص
                summary_data = {
                    "Parameter": ["Project Code", "Project Name", "Layer", "Unit System", "Max Density",
                                  "Reference Point", "Reference Passes", "Initial Compaction", "Final Compaction",
                                  "Average Compaction", "Min Compaction", "Max Compaction", "Total Points", "Date"],
                    "Value": [project_code, project_name, layer_number, 
                              "Metric" if unit_system == "metric" else "Imperial",
                              st.session_state.unit_converter.density_display(max_density_input),
                              f"{ref_latitude:.6f}, {ref_longitude:.6f}" if st.session_state.reference_data else "Not set",
                              reference_passes, f"{initial_compaction}%", f"{final_compaction}%",
                              f"{df['Compaction_Modulus_%'].mean():.1f}%", f"{df['Compaction_Modulus_%'].min():.1f}%",
                              f"{df['Compaction_Modulus_%'].max():.1f}%", len(df), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            st.download_button(
                label="📥 تحميل",
                data=output.getvalue(),
                file_name=f"FMA_Data_{project_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    with col2:
        if st.button("🗺️ تصدير الخريطة (HTML)", use_container_width=True):
            fig.write_html(f"FMA_Map_{project_code}.html")
            with open(f"FMA_Map_{project_code}.html", "r") as f:
                st.download_button("📥 تحميل الخريطة", f.read(), file_name=f"FMA_Map_{project_code}.html", mime="text/html")

else:
    if st.session_state.is_tracking:
        st.info("📍 جاري انتظار إشارة GPS... حرك الهاتف في مكان مفتوح")
    else:
        st.info("💡 اضغط 'بدء التتبع' وحرك هاتفك مع المعدة - سيتم التسجيل تلقائياً")

# ==================== تعليمات التشغيل ====================
with st.expander("📖 تعليمات التشغيل", expanded=False):
    st.markdown(f"""
    ### كيفية استخدام التطبيق (نظام {'متري' if unit_system == 'metric' else 'إمبراطوري'})
    
    1. **السماح بالوصول إلى الموقع** - عندما يطلب المتصفح الإذن، اضغط "سماح"
    
    2. **تعيين النقطة المرجعية** - قف في موقع معروف واضغط على الزر
    
    3. **بدء التتبع التلقائي** - اضغط على زر "بدء التتبع"
    
    4. **تحريك المعدة** - تحرك مع المعدة، سيتم تسجيل النقاط تلقائياً كل {st.session_state.unit_converter.format_distance(spacing_threshold)}
    
    5. **مراقبة الخريطة** - ستظهر النقاط على الخريطة مع ألوان حسب جودة الدمك
    
    ### إعدادات التسجيل التلقائي:
    - **مسافة التباعد**: {st.session_state.unit_converter.format_distance(spacing_threshold)}
    - **فترة التحديث**: {auto_record_interval} ثانية
    - **دقة GPS المطلوبة**: {min_accuracy} متر
    
    ### تفسير الألوان:
    - 🔴 أحمر: معامل دمك أقل من 80% (ضعيف)
    - 🟡 أصفر/برتقالي: 80-95% (متوسط)
    - 🟢 أخضر: 95-100% (جيد)
    - 🔵 أزرق/نيلي: أكثر من 100% (دمك مفرط)
    """)

print("✅ FMA Auto Tracking System is running!")
