"""
================================================================================
FMA COMPACTION ANALYZER PRO - الإصدار الشامل النهائي
================================================================================
مميزات النظام:
✓ الدمك الذكي مع معايرة مرجعية
✓ تسجيل تلقائي للنقاط باستخدام GPS
✓ نظام وحدات متكامل (متري/إمبراطوري)
✓ 15 تدرج لوني للخريطة الحرارية
✓ معالجة الدمك المفرط (Over-compaction)
✓ تقارير Excel, PDF, HTML
✓ حفظ واسترجاع المشاريع
✓ تحليل إحصائي متقدم
✓ تنبيهات ذكية للمستخدم
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
import sqlite3
import json
import warnings
import matplotlib.pyplot as plt
import seaborn as sns
from PIL import Image
import time
from streamlit_js_eval import streamlit_js_eval
import hashlib
import os

warnings.filterwarnings('ignore')

# ----------------------------- إعدادات الصفحة -----------------------------
st.set_page_config(
    page_title="FMA Compaction Analyzer Pro - النظام الشامل",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------- كلاس تحويل الوحدات -----------------------------
class UnitConverter:
    """نظام تحويل الوحدات المتكامل"""
    
    UNIT_SYSTEMS = {
        "metric": {
            "name": "متري (SI)",
            "length": "متر",
            "length_short": "m",
            "density": "kg/m³",
            "area": "m²",
            "speed": "km/h",
            "to_meter": 1.0,
            "from_meter": 1.0,
            "density_factor": 1.0
        },
        "imperial": {
            "name": "إمبراطوري",
            "length": "قدم",
            "length_short": "ft",
            "density": "pcf",
            "area": "ft²",
            "speed": "mph",
            "to_meter": 0.3048,
            "from_meter": 3.28084,
            "density_factor": 0.06242796
        }
    }
    
    def __init__(self, system="metric"):
        self.system = system
        self.config = self.UNIT_SYSTEMS[system]
    
    def format_length(self, meters):
        """تنسيق الطول"""
        value = meters * self.config["from_meter"]
        if self.system == "metric":
            if value >= 1000:
                return f"{value/1000:.2f} km"
            return f"{value:.1f} {self.config['length_short']}"
        else:
            if value >= 5280:
                return f"{value/5280:.2f} mi"
            return f"{value:.1f} {self.config['length_short']}"
    
    def format_speed(self, mps):
        """تنسيق السرعة"""
        if self.system == "metric":
            return f"{mps * 3.6:.1f} {self.config['speed']}"
        else:
            return f"{mps * 2.23694:.1f} {self.config['speed']}"
    
    def format_area(self, sq_meters):
        """تنسيق المساحة"""
        value = sq_meters * self.config["from_meter"] ** 2
        return f"{value:.1f} {self.config['area']}"
    
    def format_density(self, kg_m3):
        """تنسيق الكثافة"""
        if self.system == "metric":
            return f"{kg_m3:.0f} {self.config['density']}"
        else:
            return f"{kg_m3 * self.config['density_factor']:.1f} {self.config['density']}"
    
    def to_meters(self, value):
        """تحويل قيمة المستخدم إلى متر"""
        return value * self.config["to_meter"]
    
    def from_meters(self, meters):
        """تحويل من متر إلى وحدة المستخدم"""
        return meters * self.config["from_meter"]

# ----------------------------- كلاس إدارة قاعدة البيانات -----------------------------
class DatabaseManager:
    """إدارة قاعدة البيانات للمشاريع"""
    
    def __init__(self, db_path="fma_compaction.db"):
        self.db_path = db_path
        self.init_tables()
    
    def init_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # جدول المشاريع
        c.execute('''CREATE TABLE IF NOT EXISTS projects
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      project_id TEXT UNIQUE,
                      project_name TEXT,
                      date TEXT,
                      location TEXT,
                      engineer TEXT,
                      unit_system TEXT,
                      data_json TEXT,
                      summary_json TEXT,
                      thumbnail BLOB)''')
        
        # جدول المعايرة
        c.execute('''CREATE TABLE IF NOT EXISTS calibrations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      project_id TEXT,
                      ref_lat REAL,
                      ref_lon REAL,
                      initial_comp REAL,
                      ref_passes INTEGER,
                      final_comp REAL,
                      initial_moisture REAL,
                      omc REAL,
                      efficiency REAL,
                      soil_type TEXT,
                      FOREIGN KEY (project_id) REFERENCES projects(project_id))''')
        
        conn.commit()
        conn.close()
    
    def save_project(self, project_id, project_name, location, engineer, unit_system, data, summary):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO projects 
                     (project_id, project_name, date, location, engineer, unit_system, data_json, summary_json)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (project_id, project_name, datetime.now().isoformat(), location, engineer, 
                   unit_system, json.dumps(data), json.dumps(summary)))
        conn.commit()
        conn.close()
    
    def get_all_projects(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT project_id, project_name, date, location FROM projects ORDER BY date DESC")
        projects = c.fetchall()
        conn.close()
        return projects
    
    def load_project(self, project_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT data_json, summary_json FROM projects WHERE project_id = ?", (project_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return json.loads(result[0]), json.loads(result[1])
        return None, None

# ----------------------------- دوال الحسابات الهندسية المتقدمة -----------------------------
class CompactionCalculator:
    """حسابات الدمك المتقدمة"""
    
    @staticmethod
    def calculate_modulus(passes, moisture, ref_passes, ref_initial, ref_final, omc, efficiency, initial, soil_type="رملية"):
        """حساب معامل الدمك المتقدم"""
        
        # عوامل التربة
        soil_factors = {
            "رملية": {"energy": 1.0, "moisture_sensitivity": 0.06, "max_improvement": 1.3},
            "طينية": {"energy": 0.85, "moisture_sensitivity": 0.10, "max_improvement": 1.2},
            "غرينية": {"energy": 0.90, "moisture_sensitivity": 0.08, "max_improvement": 1.25},
            "صخرية مكسرة": {"energy": 1.15, "moisture_sensitivity": 0.04, "max_improvement": 1.15}
        }
        
        soil = soil_factors.get(soil_type, soil_factors["رملية"])
        eff = efficiency / 100.0
        
        # الطاقة النسبية
        energy_current = math.log1p(passes * eff * soil["energy"])
        energy_ref = math.log1p(ref_passes * eff * soil["energy"])
        energy_ratio = min(energy_current / max(energy_ref, 0.001), soil["max_improvement"])
        
        # تأثير الرطوبة
        moisture_factor = math.exp(-soil["moisture_sensitivity"] * abs(moisture - omc))
        moisture_factor = max(0.65, min(1.0, moisture_factor))
        
        # التحسن
        improvement_ref = ref_final - ref_initial
        current_improvement = improvement_ref * energy_ratio * moisture_factor
        
        result = initial + current_improvement
        return round(min(result, 112.0), 2)
    
    @staticmethod
    def get_color(value):
        """الحصول على اللون حسب القيمة (15 تدرج)"""
        if value < 40: return "#8B0000"
        elif value < 50: return "#B22222"
        elif value < 60: return "#DC143C"
        elif value < 65: return "#FF4500"
        elif value < 70: return "#FF6347"
        elif value < 75: return "#FF8C00"
        elif value < 80: return "#FFA500"
        elif value < 85: return "#FFD700"
        elif value < 88: return "#FFFF00"
        elif value < 91: return "#ADFF2F"
        elif value < 94: return "#7CFC00"
        elif value < 97: return "#32CD32"
        elif value < 100: return "#228B22"
        elif value < 105: return "#1E90FF"
        elif value < 110: return "#191970"
        else: return "#4B0082"
    
    @staticmethod
    def get_status(value, target_min=95, target_max=100):
        """تحديد حالة النقطة"""
        if value < target_min:
            return "🔴 غير مقبول", "poor"
        elif value <= target_max:
            return "🟢 مقبول", "good"
        else:
            return "🔵 دمك مفرط", "over"

# ----------------------------- دوال المسافة -----------------------------
def calculate_distance(lat1, lon1, lat2, lon2):
    """حساب المسافة بالأمتار باستخدام Haversine"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ----------------------------- دوال التقارير -----------------------------
class ReportGenerator:
    """توليد التقارير بأنواع مختلفة"""
    
    @staticmethod
    def to_excel(df, ref_data, project_data, unit_converter):
        """تصدير إلى Excel"""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Compaction_Data', index=False)
            
            summary = {
                "Parameter": ["Project ID", "Project Name", "Date", "Unit System", "Reference Point",
                              "Initial Compaction", "Reference Passes", "Final Compaction",
                              "Average Compaction", "Min Compaction", "Max Compaction", "Std Dev",
                              "Points Passed", "Points Failed", "Points Over-compacted", "Total Points"],
                "Value": [
                    project_data.get("id", ""), project_data.get("name", ""), datetime.now().strftime("%Y-%m-%d"),
                    unit_converter.config["name"], f"{ref_data.get('lat', 0):.6f}, {ref_data.get('lon', 0):.6f}",
                    f"{ref_data.get('initial', 0)}%", ref_data.get('passes', 0), f"{ref_data.get('final', 0)}%",
                    f"{df['Compaction_Modulus_%'].mean():.1f}%", f"{df['Compaction_Modulus_%'].min():.1f}%",
                    f"{df['Compaction_Modulus_%'].max():.1f}%", f"{df['Compaction_Modulus_%'].std():.2f}",
                    len(df[df['Status_Type'] == 'good']), len(df[df['Status_Type'] == 'poor']),
                    len(df[df['Status_Type'] == 'over']), len(df)
                ]
            }
            pd.DataFrame(summary).to_excel(writer, sheet_name='Summary', index=False)
            
            # توزيع الجودة
            distribution = df['Status_Type'].value_counts().reset_index()
            distribution.columns = ['Status', 'Count']
            distribution.to_excel(writer, sheet_name='Quality_Distribution', index=False)
        
        return output.getvalue()
    
    @staticmethod
    def to_html(df, ref_data, project_data, unit_converter):
        """توليد تقرير HTML"""
        good_count = len(df[df['Status_Type'] == 'good'])
        poor_count = len(df[df['Status_Type'] == 'poor'])
        over_count = len(df[df['Status_Type'] == 'over'])
        
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head><meta charset="UTF-8"><title>تقرير FMA للدمك</title>
        <style>
            body {{ font-family: 'Cairo', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
            .stat-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; text-align: center; }}
            .stat-value {{ font-size: 28px; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: right; }}
            th {{ background: #2c3e50; color: white; }}
            .good {{ color: green; }} .poor {{ color: red; }} .over {{ color: blue; }}
        </style>
        </head>
        <body>
        <div class="container">
            <h1>🏗️ FMA Compaction Analyzer Pro</h1>
            <h3>تقرير فني معتمد</h3>
            <p><strong>المشروع:</strong> {project_data.get('name', 'N/A')}</p>
            <p><strong>التاريخ:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>نظام القياس:</strong> {unit_converter.config['name']}</p>
            
            <div class="stats">
                <div class="stat-card"><div class="stat-value">{len(df)}</div><div>عدد النقاط</div></div>
                <div class="stat-card"><div class="stat-value">{df['Compaction_Modulus_%'].mean():.1f}%</div><div>المتوسط</div></div>
                <div class="stat-card"><div class="stat-value">{good_count}</div><div>مقبول</div></div>
                <div class="stat-card"><div class="stat-value">{poor_count + over_count}</div><div>غير مقبول</div></div>
            </div>
            
            <h2>📊 ملخص النتائج</h2>
            <table>
                <tr><th>المؤشر</th><th>القيمة</th></tr>
                <tr><td>أعلى معامل دمك</td><td>{df['Compaction_Modulus_%'].max():.1f}%</td></tr>
                <tr><td>أدنى معامل دمك</td><td>{df['Compaction_Modulus_%'].min():.1f}%</td></tr>
                <tr><td>الانحراف المعياري</td><td>{df['Compaction_Modulus_%'].std():.2f}</td></tr>
            </table>
            
            <h2>🎨 توزيع الجودة</h2>
            <table>
                <tr><th>الحالة</th><th>العدد</th><th>النسبة</th></tr>
                <tr class="good"><td>✅ مقبول</td><td>{good_count}</td><td>{good_count/len(df)*100:.1f}%</td></tr>
                <tr class="poor"><td>❌ غير مقبول</td><td>{poor_count}</td><td>{poor_count/len(df)*100:.1f}%</td></tr>
                <tr class="over"><td>⚠️ دمك مفرط</td><td>{over_count}</td><td>{over_count/len(df)*100:.1f}%</td></tr>
            </table>
            
            <p style="margin-top: 30px; text-align: center; color: #7f8c8d;">تم إنشاء هذا التقرير بواسطة FMA System</p>
        </div>
        </body>
        </html>
        """
        return html

# ----------------------------- تهيئة حالة الجلسة -----------------------------
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.tracking_points = []
    st.session_state.is_tracking = False
    st.session_state.last_position = None
    st.session_state.passes_count = {}
    st.session_state.reference_data = None
    st.session_state.project_data = None
    st.session_state.unit_converter = UnitConverter("metric")
    st.session_state.db_manager = DatabaseManager()
    st.session_state.calculator = CompactionCalculator()
    st.session_state.report_gen = ReportGenerator()
    st.session_state.auto_record_enabled = False
    st.session_state.last_gps_time = 0

# ----------------------------- الشريط الجانبي -----------------------------
with st.sidebar:
    st.markdown("## 🏗️ FMA الدمك الذكي")
    st.markdown("### النظام الشامل المتكامل")
    st.markdown("---")
    
    # تبويبات الشريط الجانبي
    side_tab1, side_tab2, side_tab3 = st.tabs(["📋 مشروع", "⚙️ إعدادات", "💾 المشاريع"])
    
    with side_tab1:
        project_id = st.text_input("معرف المشروع", value=f"FMA-{datetime.now().strftime('%Y%m%d%H%M')}")
        project_name = st.text_input("اسم المشروع", value="مشروع طريق رئيسي")
        project_location = st.text_input("الموقع", value="محافظة إب - اليمن")
        engineer_name = st.text_input("اسم المهندس", value="د. أحمد العرامي")
        layer_number = st.number_input("رقم الطبقة", min_value=1, value=1)
    
    with side_tab2:
        # نظام الوحدات
        unit_system = st.selectbox(
            "نظام القياس",
            ["metric", "imperial"],
            format_func=lambda x: "🇪🇺 متري (متر، كجم)" if x == "metric" else "🇺🇸 إمبراطوري (قدم، رطل)"
        )
        if unit_system != st.session_state.unit_converter.system:
            st.session_state.unit_converter = UnitConverter(unit_system)
        
        st.markdown("---")
        
        # نوع التربة
        soil_type = st.selectbox("نوع التربة", ["رملية", "طينية", "غرينية", "صخرية مكسرة"])
        
        # إعدادات التتبع
        spacing_user = st.number_input(
            f"مسافة التباعد ({st.session_state.unit_converter.config['length']})",
            min_value=1.0, value=5.0 if unit_system == "metric" else 16.0, step=0.5
        )
        spacing_meters = st.session_state.unit_converter.to_meters(spacing_user)
        
        auto_interval = st.slider("فترة تحديث GPS (ثانية)", 0.5, 5.0, 1.0, 0.5)
        min_accuracy = st.slider("الحد الأدنى لدقة GPS (متر)", 5, 50, 15)
    
    with side_tab3:
        st.markdown("### المشاريع المحفوظة")
        projects = st.session_state.db_manager.get_all_projects()
        if projects:
            for proj in projects:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"📁 **{proj[1]}**")
                    st.caption(f"   🗓️ {proj[2][:10]} | 📍 {proj[3]}")
                with col2:
                    if st.button("تحميل", key=f"load_{proj[0]}"):
                        data, summary = st.session_state.db_manager.load_project(proj[0])
                        if data:
                            st.session_state.tracking_points = data.get('points', [])
                            st.success(f"✅ تم تحميل {len(st.session_state.tracking_points)} نقطة")
                            st.rerun()
                st.divider()
        else:
            st.info("لا توجد مشاريع محفوظة")

# ----------------------------- الواجهة الرئيسية -----------------------------
st.title("🏗️ FMA Compaction Analyzer Pro")
st.markdown(f"#### *الدمك الذكي | تسجيل تلقائي | تقارير شاملة | نظام {st.session_state.unit_converter.config['name']}*")

# عرض معلومات سريعة
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📍 النقاط المسجلة", len(st.session_state.tracking_points))
with col2:
    st.metric("🎯 حالة التتبع", "🟢 نشط" if st.session_state.is_tracking else "⏸️ متوقف")
with col3:
    if st.session_state.reference_data:
        st.metric("✅ المعايرة", "مكتملة")
    else:
        st.metric("⚠️ المعايرة", "غير مكتملة")
with col4:
    st.metric("📏 نظام القياس", st.session_state.unit_converter.config['name'])

st.markdown("---")

# ==================== المعايرة ====================
with st.expander("🔧 المعايرة المرجعية (خطوة أساسية)", expanded=not st.session_state.reference_data):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📍 النقطة المرجعية")
        ref_lat = st.number_input("خط العرض المرجعي", format="%.8f", value=13.9633333)
        ref_lon = st.number_input("خط الطول المرجعي", format="%.8f", value=44.5819444)
        
        if st.button("📍 استخدام موقعي الحالي", use_container_width=True):
            loc = streamlit_js_eval(js_expressions='''
                new Promise((resolve) => {
                    navigator.geolocation.getCurrentPosition(
                        (p) => resolve({lat: p.coords.latitude, lon: p.coords.longitude}),
                        (e) => resolve(null)
                    );
                })
            ''', key='get_current_loc')
            if loc and loc.get('lat'):
                ref_lat, ref_lon = loc['lat'], loc['lon']
                st.success(f"تم تحديث الموقع: {ref_lat:.6f}, {ref_lon:.6f}")
                st.rerun()
    
    with col2:
        st.markdown("#### 📊 قيم الدمك")
        initial_comp = st.number_input("معامل الدمك الابتدائي (%)", 50.0, 90.0, 78.0)
        ref_passes = st.number_input("عدد دورات الدمك المرجعية", 1, 30, 8)
        final_comp = st.number_input("معامل الدمك النهائي (%)", 80.0, 112.0, 98.5)
        initial_moisture = st.number_input("الرطوبة الابتدائية (%)", 5.0, 25.0, 11.2)
        omc = st.number_input("الرطوبة المثلى OMC (%)", 5.0, 30.0, 12.5)
        efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)
    
    if st.button("✅ تأكيد المعايرة وحفظها", type="primary", use_container_width=True):
        st.session_state.reference_data = {
            "lat": ref_lat, "lon": ref_lon, "initial": initial_comp,
            "passes": ref_passes, "final": final_comp,
            "initial_moisture": initial_moisture, "omc": omc,
            "efficiency": efficiency, "soil_type": soil_type
        }
        st.session_state.project_data = {
            "id": project_id, "name": project_name, "location": project_location,
            "engineer": engineer_name, "layer": layer_number
        }
        st.success("✅ تم حفظ المعايرة بنجاح! يمكنك الآن بدء التتبع.")
        st.rerun()

# ==================== أزرار التحكم الرئيسية ====================
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("▶️ بدء التتبع التلقائي", type="primary", use_container_width=True):
        if st.session_state.reference_data is None:
            st.error("❌ يرجى إكمال المعايرة أولاً")
        else:
            st.session_state.is_tracking = True
            st.session_state.auto_record_enabled = True
            st.session_state.tracking_points = []
            st.session_state.passes_count = {}
            st.session_state.last_position = None
            st.success("✅ بدء التتبع التلقائي - حرك الهاتف مع المعدة")
            st.rerun()

with col2:
    if st.button("⏹️ إيقاف التتبع", use_container_width=True):
        st.session_state.is_tracking = False
        st.session_state.auto_record_enabled = False
        st.warning("⏸️ تم إيقاف التتبع")
        st.rerun()

with col3:
    if st.button("💾 حفظ المشروع", use_container_width=True):
        if st.session_state.tracking_points:
            data = {"points": st.session_state.tracking_points}
            summary = {"total_points": len(st.session_state.tracking_points)}
            st.session_state.db_manager.save_project(
                project_id, project_name, project_location, engineer_name,
                unit_system, data, summary
            )
            st.success(f"✅ تم حفظ المشروع {project_name}")
        else:
            st.warning("لا توجد نقاط لحفظها")

with col4:
    if st.button("🗑️ مسح الكل", use_container_width=True):
        st.session_state.tracking_points = []
        st.session_state.passes_count = {}
        st.session_state.last_position = None
        st.success("🗑️ تم مسح جميع النقاط")
        st.rerun()

with col5:
    if st.button("📊 تصدير التقرير", use_container_width=True):
        if st.session_state.tracking_points:
            st.session_state.show_export = True
        else:
            st.warning("لا توجد بيانات للتصدير")

# ==================== التتبع التلقائي ====================
if st.session_state.is_tracking and st.session_state.auto_record_enabled:
    st.info(f"📍 **جاري التتبع التلقائي** | التسجيل كل {st.session_state.unit_converter.format_length(spacing_meters)} | دقة GPS مطلوبة: {min_accuracy}m")
    
    # الحصول على موقع GPS
    gps_data = streamlit_js_eval(
        js_expressions='''
        new Promise((resolve) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (p) => resolve({lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy, time: Date.now()}),
                    (e) => resolve(null),
                    {enableHighAccuracy: true, timeout: 10000}
                );
            } else {
                resolve(null);
            }
        })
        ''',
        key=f'gps_{int(time.time() * 1000)}',
        debounce=auto_interval
    )
    
    if gps_data and gps_data.get('lat'):
        current_lat = gps_data['lat']
        current_lon = gps_data['lon']
        current_acc = gps_data.get('acc', 100)
        
        # عرض معلومات GPS
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📍 خط العرض", f"{current_lat:.6f}")
        with col2:
            st.metric("📍 خط الطول", f"{current_lon:.6f}")
        with col3:
            st.metric("🎯 دقة GPS", f"{current_acc:.1f} متر")
        
        # التحقق من الدقة والمسافة
        if current_acc <= min_accuracy:
            should_record = False
            if st.session_state.last_position is None:
                should_record = True
            else:
                dist = calculate_distance(
                    st.session_state.last_position[0], st.session_state.last_position[1],
                    current_lat, current_lon
                )
                if dist >= spacing_meters:
                    should_record = True
                    st.info(f"📏 تم قطع {st.session_state.unit_converter.format_length(dist)} - جاري التسجيل...")
            
            if should_record:
                point_key = f"{round(current_lat, 5)}_{round(current_lon, 5)}"
                passes = st.session_state.passes_count.get(point_key, 0) + 1
                st.session_state.passes_count[point_key] = passes
                
                if st.session_state.reference_data:
                    ref = st.session_state.reference_data
                    comp = CompactionCalculator.calculate_modulus(
                        passes, ref['initial_moisture'], ref['passes'],
                        ref['initial'], ref['final'], ref['omc'],
                        ref['efficiency'], ref['initial'], ref.get('soil_type', 'رملية')
                    )
                else:
                    comp = 85.0
                
                status_text, status_type = CompactionCalculator.get_status(comp)
                
                new_point = {
                    "Point_ID": f"P{len(st.session_state.tracking_points)+1}",
                    "Latitude": current_lat, "Longitude": current_lon,
                    "Passes": passes, "Compaction_Modulus_%": comp,
                    "Color": CompactionCalculator.get_color(comp),
                    "Status": status_text, "Status_Type": status_type,
                    "Accuracy_m": round(current_acc, 1),
                    "Timestamp": datetime.now().strftime("%H:%M:%S")
                }
                
                st.session_state.tracking_points.append(new_point)
                st.session_state.last_position = (current_lat, current_lon)
                st.success(f"✅ تم تسجيل النقطة {len(st.session_state.tracking_points)} (معامل الدمك: {comp:.1f}%)")
                time.sleep(0.3)
                st.rerun()
        else:
            st.warning(f"⚠️ دقة GPS منخفضة ({current_acc:.0f}m > {min_accuracy}m). انتظر لتحسين الإشارة.")
    else:
        st.warning("⏳ انتظار إشارة GPS... تأكد من تشغيل الموقع في هاتفك")

# ==================== عرض البيانات ====================
if st.session_state.tracking_points:
    df = pd.DataFrame(st.session_state.tracking_points)
    
    st.subheader(f"📍 البيانات المسجلة ({len(df)} نقطة)")
    st.dataframe(df[["Point_ID", "Latitude", "Longitude", "Passes", "Compaction_Modulus_%", "Status", "Timestamp"]], 
                 use_container_width=True, height=250)
    
    # الخريطة الحرارية
    st.subheader("🗺️ الخريطة الحرارية - مسار المعدة")
    
    fig = px.scatter_mapbox(
        df, lat="Latitude", lon="Longitude", color="Compaction_Modulus_%",
        size=[15]*len(df), size_max=25,
        color_continuous_scale=[
            (0.00, "#8B0000"), (0.10, "#DC143C"), (0.20, "#FF4500"),
            (0.30, "#FF8C00"), (0.40, "#FFD700"), (0.50, "#FFFF00"),
            (0.60, "#ADFF2F"), (0.70, "#7CFC00"), (0.80, "#32CD32"),
            (0.85, "#228B22"), (0.90, "#1E90FF"), (1.00, "#4B0082")
        ],
        range_color=[60, 110], zoom=17,
        center={"lat": df['Latitude'].mean(), "lon": df['Longitude'].mean()},
        mapbox_style="carto-positron",
        title=f"مسار المعدة - {len(df)} نقطة | {st.session_state.unit_converter.config['name']}",
        hover_data={"Point_ID": True, "Passes": True, "Compaction_Modulus_%": ":.1f"}
    )
    
    # إضافة خط المسار
    fig.add_trace(go.Scattermapbox(
        lat=df['Latitude'].tolist(), lon=df['Longitude'].tolist(),
        mode='lines+markers', marker=dict(size=8, color='gray'),
        line=dict(width=2, color='darkgray'), name='📍 المسار'
    ))
    
    # النقطة المرجعية
    if st.session_state.reference_data:
        ref = st.session_state.reference_data
        fig.add_trace(go.Scattermapbox(
            lat=[ref['lat']], lon=[ref['lon']],
            mode="markers", marker=dict(size=20, symbol="star", color="gold"),
            name="⭐ النقطة المرجعية"
        ))
    
    fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0}, height=550)
    st.plotly_chart(fig, use_container_width=True)
    
    # إحصائيات
    st.subheader("📊 إحصائيات وتحليلات")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("📊 المتوسط", f"{df['Compaction_Modulus_%'].mean():.1f}%")
    with col2: st.metric("📈 الأعلى", f"{df['Compaction_Modulus_%'].max():.1f}%")
    with col3: st.metric("📉 الأدنى", f"{df['Compaction_Modulus_%'].min():.1f}%")
    with col4: st.metric("📐 الانحراف", f"{df['Compaction_Modulus_%'].std():.2f}")
    with col5: 
        good = len(df[df['Status_Type'] == 'good'])
        st.metric("✅ المقبول", f"{good}/{len(df)}")
    
    # رسم بياني للتوزيع
    fig_hist = px.histogram(df, x="Compaction_Modulus_%", nbins=20,
                            title="توزيع قيم معامل الدمك",
                            labels={"Compaction_Modulus_%": "معامل الدمك (%)", "count": "عدد النقاط"})
    fig_hist.add_vline(x=95, line_dash="dash", line_color="green", annotation_text="الهدف 95%")
    st.plotly_chart(fig_hist, use_container_width=True)
    
    # تصدير
    if 'show_export' in st.session_state and st.session_state.show_export:
        st.subheader("📄 تصدير التقارير")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            excel_data = ReportGenerator.to_excel(df, st.session_state.reference_data, 
                                                  st.session_state.project_data, st.session_state.unit_converter)
            st.download_button("📊 Excel", excel_data, f"report_{project_id}.xlsx", 
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        with col2:
            html_report = ReportGenerator.to_html(df, st.session_state.reference_data,
                                                  st.session_state.project_data, st.session_state.unit_converter)
            st.download_button("📄 HTML", html_report, f"report_{project_id}.html", "text/html")
        
        with col3:
            fig.write_html(f"map_{project_id}.html")
            with open(f"map_{project_id}.html", "r") as f:
                st.download_button("🗺️ الخريطة", f.read(), f"map_{project_id}.html", "text/html")

# ==================== تعليمات ====================
with st.expander("📖 تعليمات التشغيل الكاملة", expanded=False):
    st.markdown(f"""
    ### 🚀 خطوات التشغيل
    
    1. **المعايرة** - أدخل قيم النقطة المرجعية (مكان معروف)
    2. **بدء التتبع** - اضغط زر "بدء التتبع التلقائي"
    3. **السماح بـ GPS** - أسمح للتطبيق بالوصول إلى موقعك
    4. **التحرك** - تحرك مع المعدة، سيتم التسجيل تلقائياً
    5. **التصدير** - بعد الانتهاء، صدر التقرير المناسب
    
    ### 📏 نظام الوحدات
    
    - **متري**: متر، كيلومتر، كجم/م³
    - **إمبراطوري**: قدم، ميل، رطل/قدم³
    
    ### 🎨 تفسير الألوان
    
    - 🔴 **أحمر**: أقل من 80% (ضعيف جداً)
    - 🟠 **برتقالي/أصفر**: 80-95% (يحتاج تحسين)
    - 🟢 **أخضر**: 95-100% (جيد - مقبول)
    - 🔵 **أزرق/نيلي**: أكثر من 100% (دمك مفرط)
    
    ### 💾 حفظ المشاريع
    
    يمكنك حفظ المشاريع واسترجاعها لاحقاً من الشريط الجانبي
    """)

st.markdown("---")
st.caption(f"🏗️ FMA Compaction Analyzer Pro v4.0 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

print("✅ FMA Compaction Complete System is running!")
