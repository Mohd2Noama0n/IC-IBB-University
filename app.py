"""
================================================================================
FMA COMPACTION ANALYZER PRO - الإصدار التلقائي الكامل
================================================================================
المميزات:
✓ تتبع GPS تلقائي مستمر
✓ تسجيل النقاط تلقائياً عند الحركة
✓ حساب عدد الدورات تلقائياً
✓ تحديث الخريطة في الوقت الفعلي
✓ تخزين محلي للمشاريع
✓ نظام كامل للدمك الذكي
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
import json
import os
from datetime import datetime
import math
import warnings
from streamlit_js_eval import streamlit_js_eval
import time
import hashlib

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction - النظام التلقائي",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------- كلاس إدارة الملفات -----------------------------
class StorageManager:
    """إدارة التخزين المحلي للمشاريع"""
    
    STORAGE_PATH = "fma_projects"
    
    @classmethod
    def init_storage(cls):
        if not os.path.exists(cls.STORAGE_PATH):
            os.makedirs(cls.STORAGE_PATH)
    
    @classmethod
    def save_project(cls, project_id, data):
        cls.init_storage()
        file_path = os.path.join(cls.STORAGE_PATH, f"{project_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    
    @classmethod
    def load_project(cls, project_id):
        file_path = os.path.join(cls.STORAGE_PATH, f"{project_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    @classmethod
    def get_all_projects(cls):
        cls.init_storage()
        projects = []
        for file in os.listdir(cls.STORAGE_PATH):
            if file.endswith('.json'):
                project_id = file.replace('.json', '')
                with open(os.path.join(cls.STORAGE_PATH, file), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    projects.append({
                        'id': project_id,
                        'name': data.get('project_name', project_id),
                        'date': data.get('created_at', ''),
                        'points': len(data.get('points', []))
                    })
        return sorted(projects, key=lambda x: x['date'], reverse=True)

# ----------------------------- دوال الحسابات الهندسية -----------------------------
def calculate_compaction_modulus(
    current_passes: int,
    current_moisture: float,
    reference_passes: int,
    reference_before: float,
    reference_after: float,
    optimum_moisture: float,
    efficiency: float,
    initial: float
) -> float:
    """حساب معامل الدمك"""
    eff = efficiency / 100.0
    
    # الطاقة النسبية
    energy_current = math.log1p(current_passes * eff)
    energy_ref = math.log1p(reference_passes * eff)
    energy_ratio = min(energy_current / max(energy_ref, 0.001), 1.5)
    
    # تأثير الرطوبة
    moisture_factor = math.exp(-0.06 * abs(current_moisture - optimum_moisture))
    moisture_factor = max(0.7, min(1.0, moisture_factor))
    
    # التحسن
    improvement = (reference_after - reference_before) * energy_ratio * moisture_factor
    result = initial + improvement
    
    return round(min(result, 112.0), 2)


def get_compaction_color(value: float) -> str:
    """لون معامل الدمك"""
    if value < 80: return "#FF0000"
    elif value < 85: return "#FF4500"
    elif value < 90: return "#FFA500"
    elif value < 95: return "#FFD700"
    elif value < 98: return "#ADFF2F"
    elif value < 100: return "#32CD32"
    elif value < 105: return "#228B22"
    else: return "#1E90FF"


def get_status(value: float, target_min: float = 95, target_max: float = 100) -> tuple:
    """حالة النقطة"""
    if value < target_min:
        return "🔴 غير مقبول", "poor"
    elif value <= target_max:
        return "🟢 مقبول", "good"
    else:
        return "🔵 دمك مفرط", "over"


def calculate_distance(lat1, lon1, lat2, lon2):
    """حساب المسافة بالأمتار"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ----------------------------- تهيئة حالة الجلسة -----------------------------
def init_session():
    if 'points' not in st.session_state:
        st.session_state.points = []
    if 'reference' not in st.session_state:
        st.session_state.reference = None
    if 'tracking' not in st.session_state:
        st.session_state.tracking = False
    if 'last_lat' not in st.session_state:
        st.session_state.last_lat = None
    if 'last_lon' not in st.session_state:
        st.session_state.last_lon = None
    if 'passes_map' not in st.session_state:
        st.session_state.passes_map = {}
    if 'gps_history' not in st.session_state:
        st.session_state.gps_history = []
    if 'auto_save' not in st.session_state:
        st.session_state.auto_save = True
    if 'current_project' not in st.session_state:
        st.session_state.current_project = None

init_session()
StorageManager.init_storage()

# ----------------------------- الشريط الجانبي -----------------------------
with st.sidebar:
    st.markdown("## 🏗️ FMA الدمك الذكي")
    st.markdown("### النظام التلقائي الكامل")
    st.markdown("---")
    
    # ===== GPS المباشر =====
    st.subheader("📍 GPS المباشر")
    
    # جلب موقع GPS بشكل مستمر
    gps_data = streamlit_js_eval(
        js_expressions='''
        new Promise((resolve) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => resolve({
                        lat: pos.coords.latitude,
                        lon: pos.coords.longitude,
                        acc: pos.coords.accuracy,
                        time: Date.now()
                    }),
                    (err) => resolve(null),
                    {enableHighAccuracy: true, timeout: 5000}
                );
            } else {
                resolve(null);
            }
        })
        ''',
        key=f'gps_{int(time.time())}',
        debounce=1000
    )
    
    if gps_data and gps_data.get('lat'):
        current_lat = gps_data['lat']
        current_lon = gps_data['lon']
        current_acc = gps_data.get('acc', 0)
        st.success(f"📍 GPS: {current_lat:.5f}, {current_lon:.5f}")
        st.caption(f"🎯 الدقة: {current_acc:.0f} متر")
        
        # تحديث تاريخ GPS للتتبع
        st.session_state.gps_history.append({
            'lat': current_lat, 'lon': current_lon, 
            'time': time.time(), 'acc': current_acc
        })
        # الاحتفاظ بآخر 100 نقطة فقط
        if len(st.session_state.gps_history) > 100:
            st.session_state.gps_history = st.session_state.gps_history[-100:]
    else:
        current_lat = 13.9633333
        current_lon = 44.5819444
        st.warning("⚠️ انتظار إشارة GPS...")
    
    st.markdown("---")
    
    # ===== المعايرة =====
    with st.expander("🔧 معايرة التربة", expanded=st.session_state.reference is None):
        ref_lat = st.number_input("خط العرض المرجعي", format="%.8f", value=current_lat)
        ref_lon = st.number_input("خط الطول المرجعي", format="%.8f", value=current_lon)
        
        if st.button("📍 استخدام الموقع الحالي", use_container_width=True):
            if gps_data and gps_data.get('lat'):
                ref_lat = gps_data['lat']
                ref_lon = gps_data['lon']
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1:
            initial_comp = st.number_input("الدمك الابتدائي (%)", value=78.0)
            ref_passes = st.number_input("عدد الدورات المرجعية", value=8)
            init_moisture = st.number_input("الرطوبة الابتدائية (%)", value=11.2)
        with col2:
            final_comp = st.number_input("الدمك النهائي (%)", value=98.5)
            omc = st.number_input("الرطوبة المثلى OMC (%)", value=12.5)
            efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)
        
        target_min = st.number_input("الهدف الأدنى (%)", value=95.0)
        target_max = st.number_input("الهدف الأعلى (%)", value=100.0)
        spacing = st.number_input("مسافة التسجيل (متر)", min_value=1.0, value=5.0)
        
        if st.button("✅ تأكيد المعايرة", type="primary", use_container_width=True):
            st.session_state.reference = {
                'lat': ref_lat, 'lon': ref_lon,
                'initial': initial_comp, 'passes': ref_passes,
                'final': final_comp, 'init_moisture': init_moisture,
                'omc': omc, 'efficiency': efficiency,
                'target_min': target_min, 'target_max': target_max,
                'spacing': spacing
            }
            st.success("✅ تم حفظ المعايرة")
            st.rerun()
    
    # ===== المشاريع المحفوظة =====
    with st.expander("💾 المشاريع المحفوظة"):
        projects = StorageManager.get_all_projects()
        if projects:
            for p in projects[:5]:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"📁 {p['name']}\n{p['date'][:10]} | {p['points']} نقطة")
                with col2:
                    if st.button("تحميل", key=f"load_{p['id']}"):
                        data = StorageManager.load_project(p['id'])
                        if data:
                            st.session_state.points = data.get('points', [])
                            st.session_state.reference = data.get('reference')
                            st.session_state.current_project = p['id']
                            st.success(f"تم تحميل {len(st.session_state.points)} نقطة")
                            st.rerun()
        else:
            st.info("لا توجد مشاريع محفوظة")
    
    # ===== إحصائيات سريعة =====
    st.markdown("---")
    if st.session_state.points:
        df = pd.DataFrame(st.session_state.points)
        st.metric("📊 عدد النقاط", len(df))
        st.metric("📈 متوسط الدمك", f"{df['compaction'].mean():.1f}%")
        if st.session_state.reference:
            good = len(df[df['compaction'] >= st.session_state.reference['target_min']])
            st.metric("✅ مقبول", f"{good}/{len(df)}")

# ----------------------------- الواجهة الرئيسية -----------------------------
st.title("🏗️ FMA نظام الدمك الذكي - التتبع التلقائي")
st.markdown("#### *يتم تسجيل النقاط تلقائياً عند الحركة | تحديث فوري للخريطة*")

# عرض حالة النظام
if st.session_state.reference:
    st.success(f"✅ المعايرة مكتملة | التسجيل التلقائي مفعل | المسافة: {st.session_state.reference['spacing']} متر")
else:
    st.warning("⚠️ يرجى إكمال المعايرة في الشريط الجانبي")

# أزرار التحكم
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("▶️ بدء التتبع", type="primary", use_container_width=True):
        st.session_state.tracking = True
        st.session_state.last_lat = None
        st.session_state.last_lon = None
        st.success("✅ بدء التتبع - حرك الهاتف")
with col2:
    if st.button("⏹️ إيقاف التتبع", use_container_width=True):
        st.session_state.tracking = False
        st.warning("⏸️ تم إيقاف التتبع")
with col3:
    if st.button("💾 حفظ المشروع", use_container_width=True):
        if st.session_state.points:
            project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            data = {
                'project_name': f"مشروع_{datetime.now().strftime('%Y%m%d')}",
                'created_at': datetime.now().isoformat(),
                'points': st.session_state.points,
                'reference': st.session_state.reference
            }
            StorageManager.save_project(project_id, data)
            st.success(f"✅ تم حفظ {len(st.session_state.points)} نقطة")
        else:
            st.warning("لا توجد نقاط للحفظ")
with col4:
    if st.button("🗑️ مسح الكل", use_container_width=True):
        st.session_state.points = []
        st.session_state.passes_map = {}
        st.session_state.last_lat = None
        st.session_state.last_lon = None
        st.success("🗑️ تم مسح جميع النقاط")
        st.rerun()

st.markdown("---")

# ===== التتبع التلقائي =====
if st.session_state.tracking and st.session_state.reference:
    ref = st.session_state.reference
    
    # تحديث الموقع الحالي من GPS
    if gps_data and gps_data.get('lat'):
        lat = gps_data['lat']
        lon = gps_data['lon']
        
        # حساب المسافة عن آخر نقطة مسجلة
        distance = 0
        if st.session_state.last_lat is not None:
            distance = calculate_distance(st.session_state.last_lat, st.session_state.last_lon, lat, lon)
        
        # عرض معلومات الحركة
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📍 الموقع", f"{lat:.6f}, {lon:.6f}")
        with col2:
            st.metric("📏 المسافة المقطوعة", f"{distance:.1f} متر")
        with col3:
            st.metric("🎯 دقة GPS", f"{gps_data.get('acc', 0):.0f} متر")
        
        # شريط تقدم المسافة
        progress = min(distance / ref['spacing'], 1.0)
        st.progress(progress, text=f"المسافة حتى التسجيل التالي: {ref['spacing'] - distance:.1f} متر" if distance < ref['spacing'] else "جاري التسجيل...")
        
        # تسجيل تلقائي عند قطع المسافة المطلوبة
        if distance >= ref['spacing']:
            # تجميع النقاط المتقاربة
            point_key = f"{round(lat, 5)}_{round(lon, 5)}"
            
            # تحديث عدد المرور على هذه النقطة
            current_passes = st.session_state.passes_map.get(point_key, 0) + 1
            st.session_state.passes_map[point_key] = current_passes
            
            # حساب معامل الدمك
            compaction = calculate_compaction_modulus(
                current_passes=current_passes,
                current_moisture=ref['init_moisture'],
                reference_passes=ref['passes'],
                reference_before=ref['initial'],
                reference_after=ref['final'],
                optimum_moisture=ref['omc'],
                efficiency=ref['efficiency'],
                initial=ref['initial']
            )
            
            status_text, status_type = get_status(compaction, ref['target_min'], ref['target_max'])
            color = get_compaction_color(compaction)
            
            # إضافة النقطة
            new_point = {
                'id': len(st.session_state.points) + 1,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'lat': lat,
                'lon': lon,
                'passes': current_passes,
                'moisture': ref['init_moisture'],
                'compaction': compaction,
                'status': status_text,
                'status_type': status_type,
                'color': color
            }
            
            st.session_state.points.append(new_point)
            st.session_state.last_lat = lat
            st.session_state.last_lon = lon
            
            # إشعار فوري
            st.toast(f"✅ تم تسجيل النقطة #{len(st.session_state.points)} | الدمك: {compaction:.1f}%", icon="📍")
            st.balloons()
            time.sleep(0.5)
            st.rerun()
        
        # تحديث آخر موقع
        st.session_state.last_lat = lat
        st.session_state.last_lon = lon
    else:
        st.warning("⏳ انتظار إشارة GPS... تأكد من تشغيل الموقع")

# ===== عرض النقاط المسجلة =====
if st.session_state.points:
    df = pd.DataFrame(st.session_state.points)
    
    # تبويبات
    tab1, tab2 = st.tabs(["🗺️ الخريطة الحرارية", "📊 البيانات والإحصائيات"])
    
    with tab1:
        st.subheader(f"🗺️ الخريطة الحرارية - {len(df)} نقطة مسجلة")
        
        # إنشاء الخريطة
        fig = px.scatter_mapbox(
            df,
            lat="lat",
            lon="lon",
            color="compaction",
            size=[15] * len(df),
            size_max=25,
            color_continuous_scale=[
                (0.00, "#FF0000"), (0.25, "#FFA500"), (0.50, "#FFD700"),
                (0.70, "#ADFF2F"), (0.85, "#32CD32"), (1.00, "#1E90FF")
            ],
            range_color=[70, 110],
            zoom=17,
            center={"lat": df['lat'].mean(), "lon": df['lon'].mean()},
            mapbox_style="carto-positron",
            title=f"مسار المعدة - {len(df)} نقطة | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            hover_data={"id": True, "passes": True, "compaction": ":.1f", "status": True}
        )
        
        # خط المسار
        fig.add_trace(
            go.Scattermapbox(
                lat=df['lat'].tolist(),
                lon=df['lon'].tolist(),
                mode='lines+markers',
                marker=dict(size=8, color='gray'),
                line=dict(width=2, color='darkgray'),
                name='مسار المعدة'
            )
        )
        
        # النقطة المرجعية
        if st.session_state.reference:
            ref = st.session_state.reference
            fig.add_trace(
                go.Scattermapbox(
                    lat=[ref['lat']],
                    lon=[ref['lon']],
                    mode="markers",
                    marker=dict(size=20, symbol="star", color="gold"),
                    name="⭐ النقطة المرجعية"
                )
            )
        
        fig.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=550)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("📊 البيانات والإحصائيات")
        
        # إحصائيات
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📊 عدد النقاط", len(df))
        with col2:
            st.metric("📈 أعلى دمك", f"{df['compaction'].max():.1f}%")
        with col3:
            st.metric("📉 أدنى دمك", f"{df['compaction'].min():.1f}%")
        with col4:
            st.metric("📐 متوسط الدمك", f"{df['compaction'].mean():.1f}%")
        with col5:
            if st.session_state.reference:
                good = len(df[df['compaction'] >= st.session_state.reference['target_min']])
                st.metric("✅ مقبول", f"{good}/{len(df)}")
        
        # جدول البيانات
        st.dataframe(
            df[["id", "timestamp", "lat", "lon", "passes", "compaction", "status"]],
            use_container_width=True,
            height=300
        )
        
        # رسم بياني للتوزيع
        fig_hist = px.histogram(
            df, x="compaction", nbins=15,
            title="توزيع قيم معامل الدمك",
            labels={"compaction": "معامل الدمك (%)", "count": "عدد النقاط"}
        )
        if st.session_state.reference:
            fig_hist.add_vline(x=st.session_state.reference['target_min'], 
                              line_dash="dash", line_color="green")
        st.plotly_chart(fig_hist, use_container_width=True)
        
        # تصدير
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Compaction_Data', index=False)
        
        st.download_button(
            label="📥 تحميل تقرير Excel",
            data=output.getvalue(),
            file_name=f"FMA_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

else:
    if st.session_state.tracking:
        st.info("📍 جاري التتبع... حرك الهاتف لتسجيل النقاط تلقائياً")
    else:
        st.info("💡 اضغط 'بدء التتبع' وحرك الهاتف مع المعدة - سيتم التسجيل تلقائياً")

# ===== تعليمات =====
with st.expander("📖 تعليمات التشغيل", expanded=False):
    st.markdown("""
    ### 🚀 كيفية استخدام النظام التلقائي
    
    1. **السماح بـ GPS** - أسمح للتطبيق بالوصول إلى موقعك
    
    2. **إكمال المعايرة** - أدخل قيم النقطة المرجعية في الشريط الجانبي
    
    3. **بدء التتبع** - اضغط زر "بدء التتبع"
    
    4. **التحرك** - تحرك مع المعدة، سيتم تسجيل النقاط تلقائياً كلما قطعت المسافة المحددة
    
    5. **مراقبة الخريطة** - تتحدث الخريطة تلقائياً مع كل نقطة جديدة
    
    6. **حفظ المشروع** - يمكنك حفظ البيانات واسترجاعها لاحقاً
    
    ### 📏 إعدادات مهمة
    
    - **مسافة التسجيل**: المسافة بين كل نقطة وأخرى (متر)
    - **كفاءة المعدة**: 100% للمعدة الجديدة، أقل للتهالك
    - **الهدف**: 95-100% هو النطاق المثالي
    
    ### 🎨 تفسير الألوان
    
    - 🔴 **أحمر**: أقل من 80% (ضعيف)
    - 🟠 **برتقالي**: 80-90% (متوسط)
    - 🟢 **أخضر**: 90-100% (جيد)
    - 🔵 **أزرق**: أكثر من 100% (دمك مفرط)
    """)

st.markdown("---")
st.caption(f"🏗️ FMA Compaction System v5.0 - تلقائي بالكامل | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
