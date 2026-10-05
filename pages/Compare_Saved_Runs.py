import json
import zipfile

import pandas as pd
import streamlit as st

from src.run_comparison import compare_run_bundles

st.set_page_config(page_title='Crypto Lending Risk Simulator · Compare Saved Runs', page_icon='⚖️', layout='wide')
st.title('Compare Saved Runs')
st.write('Upload two Cascade Tail Risk run bundles to see how modeled outcomes changed. Changes are candidate minus baseline.')
left, right = st.columns(2)
baseline = left.file_uploader('Baseline run', type=['zip'])
candidate = right.file_uploader('Candidate run', type=['zip'])
if baseline is None or candidate is None:
    st.info('Download simulation ZIPs from Cascade Tail Risk, then upload both here.')
    st.stop()
try:
    report = compare_run_bundles(baseline.getvalue(), candidate.getvalue())
except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
    st.error(f'Could not compare these run bundles: {error}')
    st.stop()

if report['paired']:
    st.success('Same lending portfolio and recorded market draws. Scenario differences are paired.')
else:
    st.warning('These runs are not paired. Summary changes compare separate outcomes; they do not isolate a settings effect.')
st.caption(f"Same portfolio: {report['same_portfolio']} · Same recorded market draws: {report['same_market_draws']}")
st.subheader('Risk Summary Changes')
st.dataframe(pd.DataFrame(report['metrics']), hide_index=True, width='stretch')
st.caption('Shares and probabilities use fractions (0.01 = one percentage point). Counts retain their original units.')
if report['paired']:
    st.subheader('Paired Scenario Changes')
    st.dataframe(pd.DataFrame(report['paired_deltas']), hide_index=True, width='stretch')
    st.caption('Mean, minimum, and maximum within-scenario changes; these are not confidence intervals.')
for label, key in [('Simulation settings', 'settings_changes'), ('Package versions', 'environment_changes'), ('Source fingerprints', 'source_changes')]:
    with st.expander(label):
        if report[key]:
            st.json(report[key])
        else:
            st.write('No recorded differences.')
st.download_button('Download comparison report', json.dumps(report, indent=2, allow_nan=False),
                   file_name='run_comparison.json', mime='application/json', on_click='ignore')
