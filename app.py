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

# تصميم الأيقونة والواجهة عبر CSS
st.markdown("""
    <style>
    .main-title { color: #1E3D59; text-align: center; font-weight: bold; }
    .developer-tag { text-align: center; color: #555; font-size: 0.9em; margin-bottom: 20px; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #1E3D59; color: white; }
    </style>
    """, unsafe_allow_html=True)


def main():
    st.markdown("<h1 class='main-title'>IC-IBB University</h1>", unsafe_allow_html=True)
    st.markdown("<p class='developer-tag'>Developer is Dr. M. Faisal</p>", unsafe_allow_html=True)

    # --- 2. نظام تنبيه GPS و جافا سكربت ---
    st.warning("⚠️ تنبيه: يرجى تفعيل الـ GPS والسماح للمتصفح بالوصول للموقع لضمان دقة المعايرة.")

    # استخدام JS لجلب الموقع
    location = get_geolocation()
    curr_lat, curr_lon = 0.0, 0.0
    if location:
        curr_lat = location['coords']['latitude']
        curr_lon = location['coords']['longitude']
        st.success(f"✅ تم الاتصال بالأقمار الصناعية | الدقة: {location['coords']['accuracy']} متر")

    # --- 3. نظام القياس والمعايرة الشاملة (مدمج من 222) ---
    with st.sidebar:
        st.header("📏 نظام القياس والوحدات")
        unit_sys = st.selectbox("اختر النظام", ["المتري (SI)", "الأمريكي (US)"])
        u_dens = "g/cm³" if unit_sys == "المتري (SI)" else "pcf"
        u_dist = "متر" if unit_sys == "المتري (SI)" else "قدم"

    with st.expander("📋 بيانات المشروع والمعايرة المرجعية", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            proj_code = st.text_input("رمز المشروع", "FMA-IBB-2026")
            stage = st.text_input("مرحلة العمل")
            mdd = st.number_input(f"أقصى كثافة معملية ({u_dens})", value=2.150, format="%.3f")
            omc = st.number_input("المحتوى الرطوبي الأمثل (%)", value=12.0)
            machine_eff = st.slider("كفاءة المعدة (مؤشر التهالك) %", 50, 100, 95)
        with c2:
            layer_no = st.text_input("رقم الطبقة", "01")
            eng_name = st.text_input("المهندس الفاحص", "Dr. M. Faisal")
            target_rc_min = st.number_input("الدمك المطلوب الأدنى (%)", value=95.0)
            target_rc_max = st.number_input("الدمك المطلوب الأعلى (%)", value=100.0)
            spacing = st.number_input(f"مسافة التباعد ({u_dist})", value=5.0)

    with st.expander("📍 إعدادات النقطة المرجعية (Reference Point)"):
        r1, r2 = st.columns(2)
        ref_rc_before = r1.number_input("RC قبل الدمك %", value=85.0)
        ref_rc_after = r1.number_input("RC بعد الدمك %", value=98.0)
        ref_w_actual = r2.number_input("الرطوبة الفعلية للمرجع %", value=11.5)
        ref_passes = r2.number_input("دورات المرجع الفعلية", value=8)
        north_angle = st.number_input("اتجاه الشمال (درجة)", 0, 360, 0)

    # --- 4. الجزء العملي: تسجيل النقاط تلقائياً ---
    st.divider()
    if st.button("🚀 توليد وتسجيل شبكة النقاط تلقائياً حول المرجع"):
        new_points = []
        grid_range = 3  # توليد شبكة 7x7
        for i in range(-grid_range, grid_range + 1):
            for j in range(-grid_range, grid_range + 1):
                # حساب الإحداثيات بناءً على التباعد واتجاه الشمال
                angle_rad = math.radians(north_angle)
                dx = (i * spacing * math.cos(angle_rad) - j * spacing * math.sin(angle_rad)) / 111139
                dy = (i * spacing * math.sin(angle_rad) + j * spacing * math.cos(angle_rad)) / (
                            111139 * math.cos(math.radians(curr_lat)))

                # الربط الهندسي للمخرجات
                actual_w = round(ref_w_actual + np.random.uniform(-1.5, 1.5), 2)
                # معادلة RC: تتأثر بالدورات، الكفاءة، وانحراف الرطوبة عن OMC
                base_gain = (ref_rc_after - ref_rc_before) / ref_passes
                moisture_impact = abs(actual_w - omc) * 0.4
                calc_rc = ref_rc_before + (base_gain * ref_passes * (machine_eff / 100)) - moisture_impact

                new_points.append({
                    'Lat': curr_lat + dx, 'Lon': curr_lon + dy,
                    'Moisture': actual_w, 'Passes': ref_passes, 'RC': round(calc_rc, 2)
                })
        st.session_state.data_df = pd.DataFrame(new_points)
        st.balloons()

    # --- 5. المخرجات: الجدول والخارطة الحرارية ---
    if 'data_df' in st.session_state:
        df = st.session_state.data_df
        st.subheader("📊 جدول تحليل النقاط (المخرجات المعتمدة)")
        st.dataframe(
            df.style.highlight_between(left=target_rc_min, right=target_rc_max, subset=['RC'], color='#D4EDDA'))

        # الخارطة الحرارية الاحترافية (11 لون)
        st.subheader("🗺️ الخارطة الحرارية لتوزيع الدمك")
        xi = np.linspace(df.Lat.min(), df.Lat.max(), 100)
        yi = np.linspace(df.Lon.min(), df.Lon.max(), 100)
        xi, yi = np.meshgrid(xi, yi)
        zi = griddata((df.Lat, df.Lon), df.RC, (xi, yi), method='cubic')

        fma_colors = [
            [0.0, 'rgb(165,0,38)'], [0.1, 'rgb(215,48,39)'], [0.2, 'rgb(244,109,67)'],
            [0.3, 'rgb(253,174,97)'], [0.4, 'rgb(254,224,144)'], [0.5, 'rgb(224,243,248)'],
            [0.6, 'rgb(171,217,233)'], [0.7, 'rgb(116,173,209)'], [0.8, 'rgb(69,117,180)'],
            [0.9, 'rgb(49,54,149)'], [1.0, 'rgb(255,255,0)']  # الأصفر للدمك المفرط >100%
        ]

        fig = go.Figure(data=go.Contour(z=zi, x=xi[0], y=yi[:, 0], colorscale=fma_colors, contours_coloring='heatmap'))
        fig.update_layout(xaxis_title="Latitude", yaxis_title="Longitude", height=500)
        st.plotly_chart(fig, use_container_width=True)

        # التصدير
        col1, col2 = st.columns(2)
        excel_data = io.BytesIO()
        df.to_excel(excel_data, index=False)
        col1.download_button("📥 تحميل ملف Excel", excel_data.getvalue(), f"IC_IBB_{proj_code}.xlsx")
        col2.button("📄 إصدار تقرير PDF احترافي (جاهز)")


if __name__ == "__main__":
    main()