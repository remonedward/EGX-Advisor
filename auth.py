"""Password protection logic for Streamlit."""
from __future__ import annotations

import hmac
import time

import streamlit as st

from config import secret


def check_password() -> bool:
    """Returns True if the user has a correct password or if no password is configured."""
    pwd = secret("APP_PASSWORD")
    if not pwd:
        # If no password is set in secrets (or no secrets file exists yet), bypass password gate
        return True

    def password_entered():
        if "login_attempts" not in st.session_state:
            st.session_state["login_attempts"] = 0

        if st.session_state["login_attempts"] >= 5:
            st.error("تم تجاوز الحد الأقصى للمحاولات.")
            time.sleep(2)
            return

        user_pwd = st.session_state.get("password", "")
        if hmac.compare_digest(user_pwd, str(pwd)):
            st.session_state["password_correct"] = True
            st.session_state.pop("password", None)
            st.session_state["login_attempts"] = 0
        else:
            st.session_state["password_correct"] = False
            st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1

    if st.session_state.get("password_correct", False):
        return True

    st.markdown(
        """
        <div style='text-align: center; margin-top: 50px;'>
            <h2>مرحباً بك في مستشار البورصة المصرية</h2>
            <p>التطبيق محمي بكلمة مرور</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input(
            "أدخل كلمة المرور:", type="password", on_change=password_entered, key="password"
        )
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("كلمة المرور غير صحيحة.")

    return False
