"""
FMA Compaction Analyzer Pro - نظام الدمك الذكي المتكامل
الإصدار النهائي 3.0
تاريخ التحديث: 2026-04-14
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
import sqlite3
import json
import warnings
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from PIL import Image
import time

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction Analyzer Pro - الدمك الذكي",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------- تهيئة قاعدة البيانات -----------------------------
def init_database():
    """تهيئة قاعدة البيانات المحلية لتخزين المشاريع"""
    conn = sqlite3.connect('fma_compaction_projects.db')
    c = conn.cursor()
    
    # جدول المشاريع
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_code TEXT UNIQUE,
                  project_name TEXT,
                  date TEXT,
                  location TEXT,
                  engineer_name TEXT,
                  data_json TEXT,
                  summary_json TEXT,
                  layer_number INTEGER)''')
    
    # جدول سجل المعايرة
    c.execute('''CREATE TABLE IF NOT EXISTS calibration_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_code TEXT,
                  date TEXT,
                  reference_lat REAL,
                  reference_lon REAL,
                  initial_compaction REAL,
                  reference_passes INTEGER,
                  final_compaction REAL,
                  machine_efficiency REAL,
                  soil_type TEXT)''')
    
    conn.commit()
    conn.close()

# استدعاء تهيئة القاعدة
init_database()

# ----------------------------- دوال الحسابات الهندسية -----------------------------
def calculate_compaction_modulus(
    current_passes: int,
    current_moisture: float,
    reference_passes: int,
    reference_compaction_before: float,
    reference_compaction_after: float,
    optimum_moisture: float,
    machine_efficiency: float,
    initial_compaction: float,
    soil_type: str = "رملية"
) -> dict:
    """
    حساب معامل الدمك مع جميع العوامل المؤثرة
    """
    
    # 1. كفاءة المعدة
    effective_efficiency = machine_efficiency / 100.0
    
    # 2. عوامل تصحيح حسب نوع التربة
    soil_factors = {
        "رملية": {"energy_factor": 1.0, "moisture_sensitivity": 0.06, "max_improvement": 1.3},
        "طينية": {"energy_factor": 0.85, "moisture_sensitivity": 0.10, "max_improvement": 1.2},
        "غرينية": {"energy_factor": 0.90, "moisture_sensitivity": 0.08, "max_improvement": 1.25},
        "صخرية مكسرة": {"energy_factor": 1.15, "moisture_sensitivity": 0.04, "max_improvement": 1.15},
        "رملية طينية": {"energy_factor": 0.95, "moisture_sensitivity": 0.09, "max_improvement": 1.22}
    }
    
    soil = soil_factors.get(soil_type, soil_factors["رملية"])
    
    # 3. حساب الطاقة النسبية
    energy_current = math.log1p(current_passes * effective_efficiency * soil["energy_factor"])
    energy_reference = math.log1p(reference_passes * effective_efficiency * soil["energy_factor"])
    
    if energy_reference <= 0:
        energy_ratio = 1.0
    else:
        energy_ratio = min(energy_current / energy_reference, soil["max_improvement"])
    
    # 4. تأثير الرطوبة
    moisture_deviation = abs(current_moisture - optimum_moisture)
    moisture_factor = math.exp(-soil["moisture_sensitivity"] * moisture_deviation)
    moisture_factor = max(0.65, min(1.0, moisture_factor))
    
    # 5. التحسن الكلي المرجعي
    total_improvement_reference = reference_compaction_after - reference_compaction_before
    
    # 6. حساب التحسن الحالي
    current_improvement = total_improvement_reference * energy_ratio * moisture_factor
    
    # 7. معامل الدمك النهائي
    compaction_modulus = initial_compaction + current_improvement
    compaction_modulus = round(min(compaction_modulus, 112.0), 2)
    
    return {
        "value": compaction_modulus,
        "energy_ratio": round(energy_ratio, 3),
        "moisture_factor": round(moisture_factor, 3),
        "soil_factor": soil["energy_factor"]
    }


def get_heatmap_color(compaction_value: float) -> str:
    """
    إرجاع اللون المناسب حسب قيمة معامل الدمك (15 تدرج)
    """
    if compaction_value < 40:
        return "#8B0000"      # أحمر غامق
    elif compaction_value < 50:
        return "#B22222"      # أحمر طوبي
    elif compaction_value < 60:
        return "#DC143C"      # قرمزي
    elif compaction_value < 65:
        return "#FF4500"      # برتقالي محمر
    elif compaction_value < 70:
        return "#FF6347"      # طماطمي
    elif compaction_value < 75:
        return "#FF8C00"      # برتقالي غامق
    elif compaction_value < 80:
        return "#FFA500"      # برتقالي
    elif compaction_value < 85:
        return "#FFD700"      # ذهبي
    elif compaction_value < 88:
        return "#FFFF00"      # أصفر
    elif compaction_value < 91:
        return "#ADFF2F"      # أصفر مخضر
    elif compaction_value < 94:
        return "#7CFC00"      # أخضر عشبي
    elif compaction_value < 97:
        return "#32CD32"      # أخضر ليموني
    elif compaction_value < 100:
        return "#228B22"      # أخضر غامق
    elif compaction_value < 105:
        return "#1E90FF"      # أزرق
    elif compaction_value < 110:
        return "#191970"      # أزرق منتصف الليل
    else:
        return "#4B0082"      # نيلي


def generate_points_grid(
    center_lat: float,
    center_lon: float,
    spacing_meters: float,
    grid_radius: int
) -> pd.DataFrame:
    """
    توليد شبكة من النقاط حول النقطة المرجعية
    """
    points = []
    
    # تحويل المسافة إلى درجات
    lat_offset_per_meter = 1.0 / 111111.0
    lon_offset_per_meter = 1.0 / (111111.0 * math.cos(math.radians(center_lat)))
    
    lat_step = spacing_meters * lat_offset_per_meter
    lon_step = spacing_meters * lon_offset_per_meter
    
    for i in range(-grid_radius, grid_radius + 1):
        for j in range(-grid_radius, grid_radius + 1):
            if i == 0 and j == 0:
                continue
            
            points.append({
                "Point_ID": f"P{i:+d}_{j:+d}",
                "Latitude": center_lat + (i * lat_step),
                "Longitude": center_lon + (j * lon_step),
                "Distance_X_m": i * spacing_meters,
                "Distance_Y_m": j * spacing_meters
            })
    
    return pd.DataFrame(points)


def simulate_field_data(
    df_points: pd.DataFrame,
    reference_passes: int,
    reference_moisture: float,
    passes_variation: int = 3,
    moisture_variation: float = 1.5
) -> pd.DataFrame:
    """
    محاكاة بيانات الحقل (عدد الدورات والرطوبة)
    """
    np.random.seed(42)
    
    passes_list = []
    moisture_list = []
    
    for idx, row in df_points.iterrows():
        # محاكاة عدد الدورات
        simulated_passes = max(1, reference_passes + np.random.randint(-passes_variation, passes_variation + 1))
        
        # محاكاة الرطوبة
        simulated_moisture = reference_moisture + np.random.uniform(-moisture_variation, moisture_variation)
        simulated_moisture = max(5.0, min(25.0, simulated_moisture))
        
        passes_list.append(simulated_passes)
        moisture_list.append(round(simulated_moisture, 2))
    
    df_points["Passes_Recorded"] = passes_list
    df_points["Moisture_Content_%"] = moisture_list
    
    return df_points

# ----------------------------- دوال التقارير -----------------------------
def export_to_excel(df_data: pd.DataFrame, ref_data: dict, project_data: dict) -> bytes:
    """تصدير البيانات إلى ملف Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # ورقة البيانات الرئيسية
        df_data.to_excel(writer, sheet_name='Compaction_Data', index=False)
        
        # ورقة ملخص المعايرة
        calibration_df = pd.DataFrame({
            'Parameter': ['Project Code', 'Project Name', 'Date', 'Reference Latitude', 'Reference Longitude',
                          'Initial Compaction (%)', 'Reference Passes', 'Final Compaction (%)',
                          'Initial Moisture (%)', 'Optimum Moisture (%)', 'Machine Efficiency (%)',
                          'Target Min (%)', 'Target Max (%)', 'Soil Type', 'Average Compaction (%)',
                          'Min Compaction (%)', 'Max Compaction (%)', 'Standard Deviation', 'Points Passed (%)'],
            'Value': [project_data.get('code', ''), project_data.get('name', ''), datetime.now().strftime('%Y-%m-%d'),
                      ref_data.get('lat', 0), ref_data.get('lon', 0), ref_data.get('initial', 0),
                      ref_data.get('passes', 0), ref_data.get('final', 0), ref_data.get('initial_moisture', 0),
                      ref_data.get('omc', 0), ref_data.get('efficiency', 0), project_data.get('target_min', 95),
                      project_data.get('target_max', 100), ref_data.get('soil_type', 'رملية'),
                      f"{df_data['Compaction_Modulus_%'].mean():.2f}", f"{df_data['Compaction_Modulus_%'].min():.2f}",
                      f"{df_data['Compaction_Modulus_%'].max():.2f}", f"{df_data['Compaction_Modulus_%'].std():.2f}",
                      f"{(df_data['Compaction_Modulus_%'] >= project_data.get('target_min', 95)).sum() / len(df_data) * 100:.1f}"]
        })
        calibration_df.to_excel(writer, sheet_name='Calibration_Summary', index=False)
        
        # ورقة الإحصائيات
        stats_df = df_data['Compaction_Modulus_%'].describe().reset_index()
        stats_df.columns = ['Statistic', 'Value']
        stats_df.to_excel(writer, sheet_name='Statistics', index=False)
    
    return output.getvalue()


def generate_html_report(df_data: pd.DataFrame, ref_data: dict, project_data: dict) -> str:
    """توليد تقرير HTML احترافي"""
    
    # حساب إحصائيات التوزيع
    ranges = [(0, 50), (50, 60), (60, 70), (70, 80), (80, 85), (85, 90), (90, 95), (95, 100), (100, 105), (105, 110), (110, 200)]
    
    distribution_rows = ""
    for low, high in ranges:
        if high == 200:
            count = len(df_data[df_data['Compaction_Modulus_%'] >= low])
            label = f"≥ {low}"
        else:
            count = len(df_data[(df_data['Compaction_Modulus_%'] >= low) & (df_data['Compaction_Modulus_%'] < high)])
            label = f"{low}-{high}"
        percentage = (count / len(df_data) * 100) if len(df_data) > 0 else 0
        distribution_rows += f"<tr><td>{label}</td><td>{count}</td><td>{percentage:.1f}%</td></tr>"
    
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>تقرير FMA للدمك الذكي</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
            body {{ font-family: 'Cairo', sans-serif; margin: 30px; background: #f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; border-bottom: 3px solid #2c3e50; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h1 {{ color: #2c3e50; margin: 0; }}
            .header h3 {{ color: #7f8c8d; margin: 5px 0 0; }}
            .section {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px; }}
            .section h2 {{ color: #2980b9; border-right: 5px solid #2980b9; padding-right: 15px; margin-top: 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: right; }}
            th {{ background: #2c3e50; color: white; }}
            .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
            .info-card {{ background: white; padding: 12px; border-radius: 8px; border-right: 4px solid #2980b9; }}
            .info-label {{ font-weight: bold; color: #2c3e50; }}
            .info-value {{ color: #555; margin-top: 5px; }}
            .stat-box {{ display: inline-block; width: 22%; margin: 1%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; text-align: center; }}
            .stat-value {{ font-size: 28px; font-weight: bold; }}
            .stat-label {{ font-size: 12px; opacity: 0.9; }}
            .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #7f8c8d; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏗️ FMA نظام الدمك الذكي المتكامل</h1>
                <h3>تقرير فني معتمد - Compaction Quality Report</h3>
                <p>تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="section">
                <h2>📋 معلومات المشروع</h2>
                <div class="info-grid">
                    <div class="info-card"><div class="info-label">رمز المشروع</div><div class="info-value">{project_data.get('code', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">اسم المشروع</div><div class="info-value">{project_data.get('name', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">عنوان المشروع</div><div class="info-value">{project_data.get('address', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">مرحلة العمل</div><div class="info-value">{project_data.get('phase', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">رقم الطبقة</div><div class="info-value">{project_data.get('layer', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">الجهة المشرفة</div><div class="info-value">{project_data.get('supervisor', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">المهندس المشرف</div><div class="info-value">{project_data.get('engineer', 'N/A')}</div></div>
                    <div class="info-card"><div class="info-label">الجهة المنفذة</div><div class="info-value">{project_data.get('executor', 'N/A')}</div></div>
                </div>
            </div>
            
            <div class="section">
                <h2>🔧 معطيات المعايرة المرجعية</h2>
                <div class="info-grid">
                    <div class="info-card"><div class="info-label">الإحداثيات المرجعية</div><div class="info-value">{ref_data.get('lat', 0):.6f}, {ref_data.get('lon', 0):.6f}</div></div>
                    <div class="info-card"><div class="info-label">معامل الدمك الابتدائي</div><div class="info-value">{ref_data.get('initial', 0)}%</div></div>
                    <div class="info-card"><div class="info-label">عدد الدورات المرجعية</div><div class="info-value">{ref_data.get('passes', 0)}</div></div>
                    <div class="info-card"><div class="info-label">معامل الدمك النهائي</div><div class="info-value">{ref_data.get('final', 0)}%</div></div>
                    <div class="info-card"><div class="info-label">الرطوبة الابتدائية</div><div class="info-value">{ref_data.get('initial_moisture', 0)}%</div></div>
                    <div class="info-card"><div class="info-label">الرطوبة المثلى OMC</div><div class="info-value">{ref_data.get('omc', 0)}%</div></div>
                    <div class="info-card"><div class="info-label">كفاءة المعدة</div><div class="info-value">{ref_data.get('efficiency', 0)}%</div></div>
                    <div class="info-card"><div class="info-label">نوع التربة</div><div class="info-value">{ref_data.get('soil_type', 'N/A')}</div></div>
                </div>
            </div>
            
            <div class="section">
                <h2>📊 إحصائيات الدمك الميداني</h2>
                <div style="text-align: center; margin: 20px 0;">
                    <div class="stat-box"><div class="stat-value">{len(df_data)}</div><div class="stat-label">عدد النقاط</div></div>
                    <div class="stat-box"><div class="stat-value">{df_data['Compaction_Modulus_%'].mean():.1f}%</div><div class="stat-label">المتوسط</div></div>
                    <div class="stat-box"><div class="stat-value">{df_data['Compaction_Modulus_%'].min():.1f}%</div><div class="stat-label">الحد الأدنى</div></div>
                    <div class="stat-box"><div class="stat-value">{df_data['Compaction_Modulus_%'].max():.1f}%</div><div class="stat-label">الحد الأقصى</div></div>
                </div>
            </div>
            
            <div class="section">
                <h2>🎨 توزيع جودة الدمك</h2>
                <table>
                    <thead>
                        <tr><th>مدى معامل الدمك (%)</th><th>عدد النقاط</th><th>النسبة المئوية</th></tr>
                    </thead>
                    <tbody>
                        {distribution_rows}
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>تم إنشاء هذا التقرير بواسطة نظام FMA للدمك الذكي - جميع الحقوق محفوظة © 2026</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content

# ----------------------------- واجهة المستخدم الرئيسية -----------------------------
# تهيئة حالة الجلسة
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.compaction_data = None
    st.session_state.reference_data = None
    st.session_state.project_data = None

# الشريط الجانبي
with st.sidebar:
    st.markdown("## 🏗️ FMA الدمك الذكي")
    st.markdown("---")
    
    # بيانات المشروع
    with st.expander("📋 بيانات المشروع", expanded=True):
        project_code = st.text_input("رمز المشروع", value=f"FMA-{datetime.now().strftime('%Y%m%d')}")
        project_name = st.text_input("اسم المشروع", value="مشروع طريق رئيسي")
        project_address = st.text_input("العنوان", value="محافظة إب - اليمن")
        project_phase = st.selectbox("مرحلة العمل", ["الأساسات", "الطبقة التحتية", "الطبقة الأساسية", "السطح النهائي"])
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1)
    
    with st.expander("🏢 الجهات المسؤولة", expanded=True):
        supervising_entity = st.text_input("الجهة المشرفة", value="وزارة الأشغال العامة")
        engineer_name = st.text_input("اسم المهندس المشرف", value="د. أحمد العرامي")
        executing_entity = st.text_input("الجهة المنفذة", value="مقاولات فهد")
    
    with st.expander("⚙️ إعدادات النظام", expanded=True):
        soil_type = st.selectbox("نوع التربة", ["رملية", "طينية", "غرينية", "صخرية مكسرة", "رملية طينية"])
        optimum_moisture = st.number_input("الرطوبة المثلى OMC (%)", min_value=5.0, max_value=30.0, value=12.5)
        target_min = st.number_input("الحد الأدنى المستهدف (%)", min_value=80.0, max_value=100.0, value=95.0)
        target_max = st.number_input("الحد الأقصى المستهدف (%)", min_value=95.0, max_value=115.0, value=100.0)
        
        machine_model = st.text_input("موديل المعدة", value="Cat CS66B")
        machine_efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100, 5)
        
        spacing = st.number_input("مسافة التباعد (متر)", min_value=1.0, max_value=20.0, value=5.0)
        grid_radius = st.slider("نصف قطر الشبكة", 1, 6, 3)

# الواجهة الرئيسية
st.title("🏗️ FMA نظام الدمك الذكي المتكامل")
st.markdown("#### *Intelligent Compaction System - مراقبة جودة الدمك في الوقت الفعلي*")

# تبويبين رئيسيين
tab1, tab2, tab3 = st.tabs(["🔧 المعايرة والتشغيل", "🗺️ الخريطة الحرارية", "📈 التقارير والتصدير"])

# ==================== TAB 1: المعايرة والتشغيل ====================
with tab1:
    st.subheader("📍 الخطوة 1: المعايرة المرجعية")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### إحداثيات النقطة المرجعية")
        ref_latitude = st.number_input("خط العرض (Latitude)", format="%.8f", value=13.9633333)
        ref_longitude = st.number_input("خط الطول (Longitude)", format="%.8f", value=44.5819444)
        
        st.markdown("#### قيم المعايرة الميدانية")
        initial_compaction = st.number_input("معامل الدمك الابتدائي (%)", min_value=50.0, max_value=90.0, value=78.0)
        reference_passes = st.number_input("عدد دورات الدمك المرجعية", min_value=1, max_value=30, value=8)
        final_compaction = st.number_input("معامل الدمك النهائي (%)", min_value=80.0, max_value=112.0, value=98.5)
    
    with col2:
        st.markdown("#### قياسات الرطوبة")
        initial_moisture = st.number_input("الرطوبة الابتدائية (%)", min_value=5.0, max_value=25.0, value=11.2)
        
        # عرض جودة المعايرة
        improvement = final_compaction - initial_compaction
        if improvement > 0:
            st.success(f"✅ التحسن المتوقع في المعايرة: {improvement:.1f}%")
        else:
            st.error("❌ خطأ: معامل الدمك النهائي يجب أن يكون أكبر من الابتدائي")
        
        st.info(f"📊 بناءً على المعايرة، كل دورة دمك إضافية تزيد المعامل بنسبة ≈ {(improvement/reference_passes):.2f}%")
    
    st.markdown("---")
    
    # زر بدء التشغيل
    if st.button("🚀 بدء رصد المسار وإنشاء الخريطة", type="primary", use_container_width=True):
        
        if final_compaction <= initial_compaction:
            st.error("❌ لا يمكن بدء التشغيل. يرجى تصحيح قيم المعايرة.")
        else:
            with st.spinner("جاري معالجة البيانات ورسم الخريطة الحرارية..."):
                
                # حفظ بيانات المعايرة
                ref_data = {
                    "lat": ref_latitude, "lon": ref_longitude,
                    "initial": initial_compaction, "passes": reference_passes,
                    "final": final_compaction, "initial_moisture": initial_moisture,
                    "omc": optimum_moisture, "efficiency": machine_efficiency,
                    "soil_type": soil_type
                }
                
                # حفظ بيانات المشروع
                project_data = {
                    "code": project_code, "name": project_name, "address": project_address,
                    "phase": project_phase, "layer": layer_number, "target_min": target_min,
                    "target_max": target_max, "supervisor": supervising_entity,
                    "engineer": engineer_name, "executor": executing_entity,
                    "machine_model": machine_model
                }
                
                st.session_state.reference_data = ref_data
                st.session_state.project_data = project_data
                
                # توليد شبكة النقاط
                points_df = generate_points_grid(ref_latitude, ref_longitude, spacing, grid_radius)
                
                # محاكاة بيانات الحقل
                points_df = simulate_field_data(points_df, reference_passes, initial_moisture)
                
                # حساب معامل الدمك لكل نقطة
                compaction_values = []
                colors_list = []
                
                for idx, row in points_df.iterrows():
                    result = calculate_compaction_modulus(
                        current_passes=int(row["Passes_Recorded"]),
                        current_moisture=row["Moisture_Content_%"],
                        reference_passes=reference_passes,
                        reference_compaction_before=initial_compaction,
                        reference_compaction_after=final_compaction,
                        optimum_moisture=optimum_moisture,
                        machine_efficiency=machine_efficiency,
                        initial_compaction=initial_compaction,
                        soil_type=soil_type
                    )
                    comp_value = result["value"]
                    compaction_values.append(comp_value)
                    colors_list.append(get_heatmap_color(comp_value))
                
                points_df["Compaction_Modulus_%"] = compaction_values
                points_df["Color"] = colors_list
                
                # تحديد الحالة
                def get_status(val):
                    if val < target_min:
                        return "🔴 غير مقبول"
                    elif val <= target_max:
                        return "🟢 مقبول"
                    else:
                        return "🔵 دمك مفرط"
                
                points_df["Status"] = points_df["Compaction_Modulus_%"].apply(get_status)
                
                st.session_state.compaction_data = points_df
                
                st.success(f"✅ تم رصد {len(points_df)} نقطة بنجاح")
                st.balloons()
    
    # عرض ملخص البيانات بعد التشغيل
    if st.session_state.compaction_data is not None:
        st.markdown("---")
        st.subheader("📋 ملخص نقاط الدمك المسجلة")
        
        df_display = st.session_state.compaction_data
        st.dataframe(
            df_display[["Point_ID", "Latitude", "Longitude", "Passes_Recorded", 
                        "Moisture_Content_%", "Compaction_Modulus_%", "Status"]],
            use_container_width=True,
            height=250
        )

# ==================== TAB 2: الخريطة الحرارية ====================
with tab2:
    if st.session_state.compaction_data is not None:
        df = st.session_state.compaction_data
        ref = st.session_state.reference_data
        
        st.subheader("🗺️ الخريطة الحرارية لجودة الدمك")
        
        # إنشاء الخريطة
        fig = px.scatter_mapbox(
            df,
            lat="Latitude",
            lon="Longitude",
            color="Compaction_Modulus_%",
            size=[12] * len(df),
            size_max=20,
            color_continuous_scale=[
                (0.00, "#8B0000"), (0.10, "#B22222"), (0.20, "#DC143C"),
                (0.30, "#FF4500"), (0.40, "#FF8C00"), (0.50, "#FFD700"),
                (0.60, "#FFFF00"), (0.65, "#ADFF2F"), (0.70, "#7CFC00"),
                (0.75, "#32CD32"), (0.80, "#228B22"), (0.85, "#1E90FF"),
                (0.90, "#191970"), (1.00, "#4B0082")
            ],
            range_color=[50, 110],
            zoom=18,
            center={"lat": ref["lat"], "lon": ref["lon"]},
            mapbox_style="carto-positron",
            title=f"مشروع: {st.session_state.project_data.get('code', 'N/A')} | الطبقة {st.session_state.project_data.get('layer', 'N/A')}",
            hover_data={"Point_ID": True, "Passes_Recorded": True, 
                       "Moisture_Content_%": True, "Compaction_Modulus_%": ":.1f"}
        )
        
        # إضافة اتجاه الشمال
        fig.add_annotation(
            x=0.02, y=0.98, xref="paper", yref="paper",
            text="↑ N", showarrow=False, font=dict(size=24, color="black"),
            bgcolor="rgba(255,255,255,0.7)", bordercolor="black", borderwidth=1
        )
        
        # إضافة النقطة المرجعية
        fig.add_trace(
            go.Scattermapbox(
                lat=[ref["lat"]],
                lon=[ref["lon"]],
                mode="markers",
                marker=dict(size=25, symbol="star", color="gold"),
                name="📍 النقطة المرجعية",
                hoverinfo="text",
                text=f"Reference Point<br>Initial: {ref['initial']}%<br>Final: {ref['final']}%<br>Passes: {ref['passes']}"
            )
        )
        
        fig.update_layout(
            margin={"r": 0, "t": 50, "l": 0, "b": 0},
            height=650,
            coloraxis_colorbar=dict(
                title="معامل الدمك (%)",
                tickvals=[50, 60, 70, 80, 85, 90, 95, 100, 105, 110],
                ticktext=["<50", "50-60", "60-70", "70-80", "80-85", "85-90", "90-95", "95-100", "100-105", "105-110"]
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # إحصائيات سريعة
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 متوسط الدمك", f"{df['Compaction_Modulus_%'].mean():.1f}%")
        with col2:
            st.metric("📈 أعلى قيمة", f"{df['Compaction_Modulus_%'].max():.1f}%")
        with col3:
            st.metric("📉 أدنى قيمة", f"{df['Compaction_Modulus_%'].min():.1f}%")
        with col4:
            passed = (df['Compaction_Modulus_%'] >= target_min).sum()
            st.metric("✅ نقاط مقبولة", f"{passed}/{len(df)}")
    
    else:
        st.info("💡 يرجى تشغيل النظام في تبويب 'المعايرة والتشغيل' أولاً")

# ==================== TAB 3: التقارير والتصدير ====================
with tab3:
    if st.session_state.compaction_data is not None:
        df = st.session_state.compaction_data
        ref = st.session_state.reference_data
        proj = st.session_state.project_data
        
        st.subheader("📄 تصدير التقارير")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # تصدير Excel
            if st.button("📊 تصدير تقرير Excel", use_container_width=True):
                excel_data = export_to_excel(df, ref, proj)
                st.download_button(
                    label="📥 تحميل ملف Excel",
                    data=excel_data,
                    file_name=f"FMA_Report_{project_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col2:
            # تصدير HTML (PDF بديل)
            if st.button("📄 تصدير تقرير HTML", use_container_width=True):
                html_report = generate_html_report(df, ref, proj)
                st.download_button(
                    label="📥 تحميل تقرير HTML",
                    data=html_report.encode('utf-8'),
                    file_name=f"FMA_Report_{project_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                    use_container_width=True
                )
        
        st.markdown("---")
        st.subheader("📊 تحليل إضافي")
        
        # رسم بياني لتوزيع القيم
        fig_hist = px.histogram(
            df, x="Compaction_Modulus_%", nbins=20,
            title="توزيع قيم معامل الدمك",
            labels={"Compaction_Modulus_%": "معامل الدمك (%)", "count": "عدد النقاط"},
            color_discrete_sequence=["#2c3e50"]
        )
        
        # إضافة خطوط الأهداف
        fig_hist.add_vline(x=target_min, line_dash="dash", line_color="green", annotation_text=f"الهدف الأدنى {target_min}%")
        fig_hist.add_vline(x=target_max, line_dash="dash", line_color="orange", annotation_text=f"الهدف الأعلى {target_max}%")
        
        st.plotly_chart(fig_hist, use_container_width=True)
        
        # جدول إحصائي مفصل
        st.subheader("📋 إحصائيات مفصلة")
        stats_df = df['Compaction_Modulus_%'].describe().reset_index()
        stats_df.columns = ['الإحصائية', 'القيمة']
        stats_df['القيمة'] = stats_df['القيمة'].map(lambda x: f"{x:.2f}%")
        st.dataframe(stats_df, use_container_width=True)
    
    else:
        st.info("💡 لا توجد بيانات للتصدير. يرجى تشغيل النظام أولاً.")

# ----------------------------- نهاية الكود -----------------------------
print("✅ FMA Compaction System is running successfully!")
