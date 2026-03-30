import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import griddata
from streamlit_js_eval import streamlit_js_eval, get_geolocation
import io
import math

# --- 1. الهوية البصرية والاسم المعتمد ---
st.set_page_config(
    page_title="IC-IBB Geotechnical",
    page_icon="👷‍♂️",
    layout="centered"
)

# تصميم الواجهة عبر CSS
st.markdown("""
    <style>
    .main-title { color: #1E3D59; text-align: center; font-weight: bold; margin-bottom: 0px; }
    .developer-tag { text-align: center; color: #555; font-size: 0.9em; margin-bottom: 20px; border-bottom: 2px solid #1E3D59; padding-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #1E3D59; color: white; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.markdown("<h1 class='main-title'>IC-IBB University</h1>", unsafe_allow_html=True)
    st.markdown("<p class='developer-tag'>Developer: Dr. M. Faisal - Geotechnical Dept.</p>", unsafe_allow_html=True)

    # --- 2. نظام الـ GPS الذكي ---
    location = get_geolocation()
    
    with st.expander("📍 إعدادات الموقع والنقطة المرجعية (Reference Point)", expanded=True):
        mode = st.radio("مصدر إحداثيات المرجع:", ["تلقائي (GPS)", "إدخال يدوي (Manual)"])
        
        c_lat, c_lon = 13.974, 44.183 # إحداثيات افتراضية لجامعة إب
        
        if mode == "تلقائي (GPS)" and location:
            c_lat = location['coords']['latitude']
            c_lon = location['coords']['longitude']
            st.success(f"✅ تم التقاط الموقع بدقة: {location['coords']['accuracy']} متر")
        
        col_gps1, col_gps2 = st.columns(2)
        ref_lat = col_gps1.number_input("خط العرض (Latitude)", value=c_lat, format="%.6f")
        ref_lon = col_gps2.number_input("خط الطول (Longitude)", value=c_lon, format="%.6f")

    # --- 3. نظام القياس والمعايرة ---
    with st.sidebar:
        st.header("📏 الإعدادات العامة")
        unit_sys = st.selectbox("النظام المستخدم", ["المتري (SI)", "الأمريكي (US)"])
        u_dens = "g/cm³" if unit_sys == "المتري (SI)" else "pcf"
        u_dist = "متر" if unit_sys == "المتري (SI)" else "قدم"

    with st.expander("📋 بيانات التربة والمعايرة"):
        c1, c2 = st.columns(2)
        with c1:
            mdd = st.number_input(f"أقصى كثافة معملية ({u_dens})", value=2.150, format="%.3f")
            omc = st.number_input("المحتوى الرطوبي الأمثل (%)", value=12.0)
            machine_eff = st.slider("كفاءة المعدة (Efficiency) %", 50, 100, 95)
        with c2:
            target_rc_min = st.number_input("الدمك المطلوب الأدنى (%)", value=95.0)
            spacing = st.number_input(f"مسافة التباعد بين النقاط ({u_dist})", value=5.0)
            north_angle = st.number_input("انحراف الشمال (درجة)", 0, 360, 0)

    with st.expander("🏗️ بيانات المرجع الميدانية"):
        r1, r2 = st.columns(2)
        ref_rc_before = r1.number_input("RC الابتدائي (قبل الدمك) %", value=85.0)
        ref_rc_after = r1.number_input("RC المستهدف للمرجع %", value=98.0)
        ref_w_actual = r2.number_input("الرطوبة الفعلية للمرجع %", value=11.5)
        ref_passes = r2.number_input("عدد دورات المعدة للمرجع", value=8)

    # --- 4. معالجة البيانات وتوليد الشبكة ---
    if st.button("🚀 توليد شبكة النقاط وتحليل الدمك"):
        new_points = []
        grid_range = 3 # شبكة 7x7
        
        for i in range(-grid_range, grid_range + 1):
            for j in range(-grid_range, grid_range + 1):
                # تحويل المسافات لإحداثيات جغرافية
                angle_rad = math.radians(north_angle)
                dx = (i * spacing * math.cos(angle_rad) - j * spacing * math.sin(angle_rad)) / 111320
                dy = (i * spacing * math.sin(angle_rad) + j * spacing * math.cos(angle_rad)) / (111320 * math.cos(math.radians(ref_lat)))
                
                # خوارزمية الدكتور فيصل للدمك
                actual_w = round(ref_w_actual + np.random.uniform(-1.2, 1.2), 2)
                base_gain = (ref_rc_after - ref_rc_before) / ref_passes
                # أثر الرطوبة: كلما ابتعدنا عن OMC قلّت الكفاءة
                moisture_impact = abs(actual_w - omc) * 0.5 
                calc_rc = ref_rc_before + (base_gain * ref_passes * (machine_eff/100)) - moisture_impact
                
                new_points.append({
                    'Latitude': ref_lat + dx, 'Longitude': ref_lon + dy,
                    'Moisture %': actual_w, 'Passes': ref_passes, 'RC %': round(calc_rc, 2)
                })
        
        st.session_state.data_df = pd.DataFrame(new_points)
        st.balloons()

    # --- 5. العرض والخارطة الحرارية ---
    if 'data_df' in st.session_state:
        df = st.session_state.data_df
        st.subheader("📊 تحليل بيانات الدمك الميداني")
        
        # تلوين الجدول بناءً على المواصفات
        st.dataframe(df.style.background_gradient(subset=['RC %'], cmap='RdYlGn'))

        # إنشاء الخارطة الحرارية
        st.subheader("🗺️ الخارطة الحرارية (Heatmap)")
        grid_x, grid_y = np.mgrid[df.Latitude.min():df.Latitude.max():100j, 
                                  df.Longitude.min():df.Longitude.max():100j]
        grid_z = griddata((df.Latitude, df.Longitude), df['RC %'], (grid_x, grid_y), method='cubic')

        fig = go.Figure(data=go.Contour(
            z=grid_z.T,
            x=np.linspace(df.Latitude.min(), df.Latitude.max(), 100),
            y=np.linspace(df.Longitude.min(), df.Longitude.max(), 100),
            colorscale=[
                [0, 'red'], [0.5, 'yellow'], [0.85, 'green'], [1, 'blue']
            ],
            colorbar=dict(title="RC %")
        ))
        fig.update_layout(xaxis_title="Latitude", yaxis_title="Longitude")
        st.plotly_chart(fig, use_container_width=True)

        # التصدير لـ Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Compaction_Report')
        
        st.download_button(
            label="📥 تحميل تقرير Excel المعتمد",
            data=output.getvalue(),
            file_name=f"IC_IBB_Report_{ref_lat}.xlsx",
            mime="application/vnd.ms-excel"
        )

if __name__ == "__main__":
    main()
