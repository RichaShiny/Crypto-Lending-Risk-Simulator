"""Bounded in-memory caches for expensive dashboard simulations."""
import streamlit as st

from src.shapley_attribution import run_shapley_tail_risk_attribution
from src.tail_risk_attribution import run_tail_risk_attribution


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def cached_attribution(positions, use_shapley=False, **settings):
    """Reuse only runs with matching portfolio, method, and simulation settings."""
    runner = run_shapley_tail_risk_attribution if use_shapley else run_tail_risk_attribution
    return runner(positions=positions, **settings)
