"""
Streamlit web app for beam_multi_span.py
------------------------------------------
Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Opens at http://localhost:8501 in your browser.
Put this file in the SAME folder as beam_multi_span.py.
"""

import datetime
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from beam_multi_span import (
    ProjectInfo, DesignCriteria, SlabPanel, WallLoad, PanelContribution, PointLoad,
    Span, BeamSystem, FINISHES_OPTIONS, LIVE_LOAD_OPTIONS, bs8110_classify_panel,
    panel_sketch_figure, beam_kind, encode_project_state, decode_project_state,
)

st.set_page_config(page_title="Multi-Span Beam Load Analysis", layout="centered")
st.title("Multi-span beam — load analysis")

# ======================================================================
# Save / reopen a project:  every input widget goes through W(), which
#  - remembers the widget key so its value can be saved, and
#  - pre-fills the widget when a saved project link (.html) is opened.
# ======================================================================
st.session_state.setdefault("_loaded", {})
st.session_state["_reg_prev"] = st.session_state.get("_reg", {})
st.session_state["_reg"] = {}


def W(where, kind, label, *args, key=None, **kw):
    if key is not None and not kw.get("disabled"):
        st.session_state["_reg"][key] = kind
        loaded = st.session_state["_loaded"]
        if key in loaded:
            v = loaded[key]
            if kind in ("text_input", "number_input", "checkbox"):
                kw["value"] = v
            elif kind == "date_input":
                kw["value"] = datetime.date.fromisoformat(v)
            elif kind in ("selectbox", "radio"):
                opts = list(kw.get("options", args[0] if args else []))
                if v in opts:
                    kw["index"] = opts.index(v)
    return getattr(where, kind)(label, *args, key=key, **kw)


def _collect_values():
    out = {}
    for k in st.session_state["_reg"]:
        if k in st.session_state:
            v = st.session_state[k]
            out[k] = v.isoformat() if isinstance(v, datetime.date) else v
    out["_v"] = 2            # version 2: distance inputs are whole millimetres
    return out


def _detect_base_url():
    try:
        u = st.context.url
        if u:
            return str(u).split("?")[0].rstrip("/")
    except Exception:
        pass
    try:
        host = st.context.headers.get("Host", "")
        if host:
            return ("http://" if host.startswith(("localhost", "127.")) else "https://") + host
    except Exception:
        pass
    return ""


_tok = st.query_params.get("p")
if _tok and st.session_state.get("_p_used") != _tok:
    try:
        _state = decode_project_state(_tok)
        st.session_state["_p_used"] = _tok
        st.query_params.clear()
        if _state.get("_v") == 2:
            st.session_state["_loaded"] = _state
        else:
            st.warning("This project link was saved by an older version of the app (distances were in metres), "
                       "so it cannot be reopened. Please enter the project again and save a new link.")
    except Exception:
        st.error("This project link could not be read — it may be incomplete or damaged.")

dc = DesignCriteria()

# ---------------- Step 1: project information ----------------
st.header("1. Project information")
c1, c2 = st.columns(2)
_d = ProjectInfo()
project = ProjectInfo(
    firm_name=W(c1, "text_input", "Firm name", value=_d.firm_name, key="proj_firm"),
    address=W(c2, "text_input", "Address", value=_d.address, key="proj_address"),
    tel=W(c1, "text_input", "Tel", value=_d.tel, key="proj_tel"),
    email=W(c2, "text_input", "Email", value=_d.email, key="proj_email"),
    project_title=W(c1, "text_input", "Project title", key="proj_title"),
    job_no=W(c2, "text_input", "Job No.", key="proj_job"),
    designer=W(c1, "text_input", "Designed by", key="proj_designer"),
    checked_by=W(c2, "text_input", "Checked by", value=_d.checked_by, key="proj_checked"),
    date=W(c1, "date_input", "Date", value=datetime.date.today(), format="DD/MM/YYYY", key="proj_date").strftime("%d/%m/%Y"),
    revision=W(c2, "text_input", "Revision", value="A", key="proj_rev"),
    floor=W(c1, "text_input", "Floor", placeholder="e.g. First Floor", key="proj_floor"),
    floor_height=W(c2, "text_input", "Floor height / level (mm)", placeholder="e.g. +3000", key="proj_floor_h"),
    beam_name=W(c1, "text_input", "Beam name", placeholder="e.g. F3", key="proj_beam"),
    along_grid=W(c2, "text_input", "Grid reference — along grid", placeholder="e.g. 1", key="proj_grid_a"),
    between_grids=W(c1, "text_input", "Grid reference — between grids", placeholder="e.g. D/1 and G/1", key="proj_grid_b"),
    material=W(c2, "text_input", "Material / beam ID", key="proj_material"),
    calc_sheet_no=W(c1, "text_input", "Calculation sheet No.", key="proj_calc_no"),
)
if project.element_text():
    st.caption(f"Element:  **{project.element_text()}**")

# ---------------- Step 2: spans ----------------
st.header("2. Spans")
n_spans = W(st, "number_input", "Number of spans", min_value=1, value=2, step=1, key="n_spans")
lengths = []
ROW_SIZE = 6  # wrap span-length inputs into rows so large counts stay usable
for row_start in range(0, int(n_spans), ROW_SIZE):
    row_indices = range(row_start, min(row_start + ROW_SIZE, int(n_spans)))
    cols = st.columns(len(row_indices))
    for col, i in zip(cols, row_indices):
        with col:
            lengths.append(W(st, "number_input", f"Span {i+1} length (mm)", min_value=100, value=3000 + 1000 * i, step=1, key=f"L{i}") / 1000.0)

c1, c2 = st.columns(2)
start_cond = W(c1, "selectbox", "Condition at FIRST support (start of Span 1)", ["Pin", "Cantilever"], key="start_cond")
end_cond = W(c2, "selectbox", "Condition at LAST support (end of last span)", ["Pin", "Cantilever"], key="end_cond")
st.caption("Interior/shared supports are always pinned and continuous.")
_title = project.drawing_title(beam_kind(int(n_spans), start_cond, end_cond))
if _title:
    st.caption(f"Calculation title:  **{_title}**")

# ---------------- Step 3 & 4: slab panels ----------------
st.header("3. Slab panels & design criteria")
n_panels = W(st, "number_input", "Number of slab panels", min_value=1, value=3, step=1, key="n_panels")
panels = {}
fin_labels = {k: v[0] for k, v in FINISHES_OPTIONS.items()}
live_labels = {k: v[0] for k, v in LIVE_LOAD_OPTIONS.items()}
used_names = set()
for i in range(1, int(n_panels) + 1):
    default_name = f"P{i}"
    name = W(st, "text_input", f"Panel {i} — name/ID", value=default_name, key=f"pname{i}")
    if name in used_names:
        st.warning(f"'{name}' is already used by another panel — please make it unique.")
    used_names.add(name)
    with st.expander(f"Panel: {name}", expanded=(i <= 2)):
        c1, c2, c3 = st.columns(3)
        t = W(c1, "number_input", "Thickness (mm)", value=200, key=f"pt{i}")
        ly = W(c2, "number_input", "ly — long dimension (mm)", value=5000, step=1, key=f"ply{i}") / 1000.0
        lx = W(c3, "number_input", "lx — short dimension (mm)", value=2000, step=1, key=f"plx{i}") / 1000.0
        if lx > ly:
            ly, lx = lx, ly
            st.info(f"ly must be the longer dimension — swapped automatically: ly={ly*1000:.0f} mm, lx={lx*1000:.0f} mm")
        ratio = ly / lx if lx > 0 else float("inf")
        spanning = "Two-way" if ratio <= 2.0 else "One-way"
        st.caption(f"ly/lx = {ratio:.2f}  ->  {'\u2264 2.0' if spanning=='Two-way' else '> 2.0'}  ->  "
                   f"**{spanning} spanning slab**")
        c4, c5 = st.columns(2)
        fin_key = W(c4, "selectbox", "Finishes", options=list(FINISHES_OPTIONS.keys()),
                                format_func=lambda k: fin_labels[k], key=f"pfin{i}")
        live_key = W(c5, "selectbox", "Live load", options=list(LIVE_LOAD_OPTIONS.keys()),
                                 format_func=lambda k: live_labels[k], key=f"pliv{i}")
        has_partition = W(st, "checkbox", "Partition wall on this panel?", key=f"ppart{i}")
        plen = pthk = pht = pfl = pdp = 0.0
        pab = "Slab"
        if has_partition:
            c6, c7 = st.columns(2)
            plen = W(c6, "number_input", "Partition length (mm)", value=5000, step=1, key=f"pplen{i}") / 1000.0
            pthk = W(c7, "number_input", "Partition thickness (mm)", value=200, step=1, key=f"ppthk{i}") / 1000.0
            c8, c9, c10 = st.columns(3)
            pfl = W(c8, "number_input", "Floor height (mm)", value=3600, step=1, key=f"ppfl{i}") / 1000.0
            pab = W(c9, "selectbox", "Above the partition", options=["Beam", "Slab", "Opening"], index=1,
                    key=f"ppab{i}")
            pdp = W(c10, "number_input", "Depth (mm)", value=int(t), step=1, key=f"ppdp{i}_{t}") / 1000.0
            pht = max(0.0, pfl - pdp)
            st.caption(f"Partition height = floor height − {pab.lower()} depth = "
                       f"{pfl*1000:.0f} − {pdp*1000:.0f} = **{pht*1000:.0f} mm**")

        st.markdown("**Distribution factor** (auto — BS 8110-1:1997 Table 3.15 for solid slabs)")
        type_opts = {"Solid slab (Table 3.15 — one-way uses beta_vx at ly/lx = 2.0)": "solid",
                     "Ribbed slab (factor 0.5, double arrow = rib span)": "ribbed",
                     "Cantilever slab (single arrow = loading direction)": "cantilever"}
        slab_type = type_opts[W(st, "selectbox", "Panel type", list(type_opts.keys()), key=f"pstype{i}")]

        st.markdown("**Panel edge on this beam — orientation**")
        st.caption("Pick the edge of this panel that sits on the beam (reference edge). It is applied "
                   "automatically to 'Panel edge on this beam' under Panel contributions. Also say whether "
                   "that edge is your ly or lx side.")
        oc1, oc2 = st.columns(2)
        primary_edge = W(oc1, "selectbox", "Reference edge", ["top", "bottom", "left", "right"],
                                      index=2, key=f"pref{i}")
        primary_edge_is_ly = W(oc2, "checkbox", f"'{primary_edge}' edge is the ly ({ly*1000:.0f} mm) side",
                                           value=False, key=f"prefly{i}")
        opposite = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[primary_edge]
        pair = {primary_edge, opposite}
        ly_edges = pair if primary_edge_is_ly else ({"top", "bottom", "left", "right"} - pair)
        lx_edges = {"top", "bottom", "left", "right"} - ly_edges

        edge_continuous = {"top": True, "bottom": True, "left": True, "right": True}
        arrow_perpendicular, arrow_flip, rib_lx = True, False, 0.525
        if slab_type in ("ribbed", "cantilever"):
            what = "Rib spanning direction (double arrow)" if slab_type == "ribbed" \
                else "Cantilever loading direction (single arrow)"
            rel = W(st, "radio", f"{what} relative to the reference edge",
                           ["Perpendicular to the reference edge", "Parallel to the reference edge"],
                           key=f"parrow{i}")
            arrow_perpendicular = rel.startswith("Perpendicular")
            if not arrow_perpendicular:
                if slab_type == "ribbed":
                    rib_lx = W(st, "number_input", "lx — rib load width (mm)", value=525, step=1,
                                              key=f"prib{i}") / 1000.0
                else:
                    arrow_flip = W(st, "checkbox", "Flip arrow direction (sketch only — no effect on load)",
                                              key=f"pflip{i}")

        panel_obj = SlabPanel(name, t, ly, lx, FINISHES_OPTIONS[fin_key][1], LIVE_LOAD_OPTIONS[live_key][1],
                              has_partition, plen, pthk, pht, slab_type, edge_continuous,
                              primary_edge, primary_edge_is_ly,
                              partition_floor_ht_m=pfl, partition_depth_m=pdp, partition_above=pab,
                              arrow_perpendicular=arrow_perpendicular, arrow_flip=arrow_flip,
                              rib_lx_m=rib_lx,
                              finishes_label=FINISHES_OPTIONS[fin_key][0],
                              live_label=LIVE_LOAD_OPTIONS[live_key][0])

        if slab_type == "solid":
            ec1, ec2 = st.columns([1, 1])
            with ec1:
                for edge_key in ("top", "bottom", "left", "right"):
                    dim = "ly" if edge_key in ly_edges else "lx"
                    dim_val = ly if dim == "ly" else lx
                    edge_continuous[edge_key] = W(st, "checkbox", 
                        f"{edge_key.capitalize()} continuous ({dim} edge, {dim_val*1000:.0f} mm)",
                        value=True, key=f"e{edge_key}{i}")
            with ec2:
                st.pyplot(panel_sketch_figure(panel_obj, units="mm"), width='content')
            st.caption(f"BS 8110 panel type: **{bs8110_classify_panel(edge_continuous, list(ly_edges), list(lx_edges))}**"
                       + (f"  — *one-way: beta_vx taken at ly/lx = 2.0*" if spanning == "One-way" else ""))
        else:
            sk1, sk2 = st.columns([1, 1])
            with sk2:
                st.pyplot(panel_sketch_figure(panel_obj, units="mm"), width='content')
            with sk1:
                f_ = panel_obj.distribution_factor(primary_edge)
                st.markdown(f"Factor = **{f_:.2f}**  \nLoad width lx = **{panel_obj.load_width_m():.3f} m**")
                if slab_type == "ribbed":
                    st.caption("Ribs perpendicular to the beam: lx = panel length along the ribs."
                               if arrow_perpendicular else
                               "Ribs parallel to the beam: lx = rib load width entered above.")
                else:
                    st.caption("Cantilever loading perpendicular to the beam (arrow points toward it): factor 1.0, lx = projection length."
                               if arrow_perpendicular else
                               "Beam runs along the cantilever direction: factor 0.5, lx = shortest panel dimension.")
        panels[name] = panel_obj
        st.caption(f"-> Gₖ = {panels[name].dead_kNm2(dc):.3f} kN/m²   Qₖ = {panels[name].live_kNm2_factored(dc):.3f} kN/m²"
                   f"  (Step 5: calculated automatically)")

# ---------------- Step 6: wall ----------------
st.header("4. Wall loading")
wall_defined = W(st, "checkbox", "Is there direct wall loading on the beam anywhere?", key="wall_defined")
if wall_defined:
    c1, c2, c3, c4 = st.columns(4)
    wt = W(c1, "number_input", "Wall thickness (mm)", value=200, step=1, key="wall_t") / 1000.0
    wfl = W(c2, "number_input", "Floor height (mm)", value=3600, step=1, key="wall_fl") / 1000.0
    wab = W(c3, "selectbox", "Above the wall", options=["Beam", "Slab", "Opening"], key="wall_above")
    wdp = W(c4, "number_input", "Depth (mm)", value=450, step=1, key="wall_dp") / 1000.0
    wall = WallLoad(wt, wfl, wdp, wab)
    st.caption(f"Wall height = floor height − {wab.lower()} depth = {wfl*1000:.0f} − {wdp*1000:.0f} = "
               f"**{wall.height_m*1000:.0f} mm**")
    st.caption(f"Factored wall dead load = {wall.factored_dead_kNm(dc):.3f} kN/m (applied where marked present)")
else:
    wall = WallLoad(0, 0)

beam = BeamSystem(dc, panels, wall, project)
labels = [chr(65 + i) for i in range(int(n_spans) + 1)]

# ---------------- Step 7 & 8: per-span distribution + point loads ----------------
st.header("5. Load distribution, self-weight and point loads per span")
for i in range(int(n_spans)):
    with st.expander(f"Span {i+1}  ({labels[i]} -> {labels[i+1]}, {lengths[i]*1000:.0f} mm)", expanded=(i == 0)):
        st.subheader("Panel contributions")
        n_c = W(st, "number_input", "Number of panel contributions", min_value=0, value=2, step=1, key=f"nc{i}")
        contributions = []
        for j in range(int(n_c)):
            c1, c2 = st.columns(2)
            pid = W(c1, "selectbox", "Panel", options=list(panels.keys()), key=f"s{i}c{j}p")
            panel = panels[pid]
            edge = panel.primary_edge
            W(c2, "selectbox", "Panel edge on this beam", options=[edge], index=0, disabled=True,
                         key=f"s{i}c{j}edge_{pid}_{edge}")
            st.caption("Set from the panel's reference edge (Step 3-4). Contributions sharing the same "
                       "edge are treated as being on the same side of the beam.")
            contributions.append(PanelContribution(pid, edge))
            factor = panel.distribution_factor(edge)
            st.caption(f"-> distribution factor = {factor:.3f}   |   Lx = {panel.load_width_m():.3f} m")

        wall_here = False
        if wall_defined:
            wall_here = W(st, "checkbox", "Wall present on this span", key=f"s{i}wall")

        self_weight = W(st, "number_input", "Element self-weight (kN/m) — added automatically to Gₖ",
                                       value=0.0, step=0.1, key=f"s{i}sw")

        st.subheader("Point loads")
        n_p = W(st, "number_input", "Number of point loads", min_value=0, value=0, step=1, key=f"np{i}")
        point_loads = []
        for j in range(int(n_p)):
            c1, c2, c3, c4 = st.columns(4)
            label = W(c1, "text_input", "Label", value=f"P{j+1}", key=f"s{i}p{j}lbl")
            d = W(c2, "number_input", "Ngₖ (kN)", value=0.0, step=0.5, key=f"s{i}p{j}d")
            l = W(c3, "number_input", "Nqₖ (kN)", value=0.0, step=0.5, key=f"s{i}p{j}l")
            x = W(c4, "number_input", "Position (mm)", value=0, step=1, key=f"s{i}p{j}x") / 1000.0
            eb = eh = el = 0.0
            if W(st, "checkbox", f"Add self-weight of the element (beam / column) to {label}", key=f"s{i}p{j}sw"):
                e1, e2, e3 = st.columns(3)
                eb = W(e1, "number_input", "Width b (mm)", value=200, step=1, key=f"s{i}p{j}eb") / 1000.0
                eh = W(e2, "number_input", "Depth h (mm)", value=450, step=1, key=f"s{i}p{j}eh") / 1000.0
                el = W(e3, "number_input", "Length (mm)", value=3000, step=1, key=f"s{i}p{j}el") / 1000.0
            pl = PointLoad(label, d, l, x, eb, eh, el, dc.concrete_density, dc.factor_selfweight_partition)
            if pl.self_weight_kN:
                st.caption(f"Self-weight = {dc.factor_selfweight_partition:g} × {eb:.3f} × {eh:.3f} × {el:.3f} × "
                           f"{dc.concrete_density:g} = {pl.self_weight_kN:.2f} kN   →   "
                           f"total Ngₖ = {d:g} + {pl.self_weight_kN:.2f} = **{pl.total_dead_kN:.2f} kN**")
            point_loads.append(pl)

        left_cond = start_cond if i == 0 else "Pin"
        right_cond = end_cond if i == int(n_spans) - 1 else "Pin"
        beam.add_span(Span(i + 1, lengths[i], labels[i], labels[i + 1],
                            contributions=contributions, wall_present=wall_here,
                            point_loads=point_loads, self_weight_kNm=self_weight,
                            left_condition=left_cond, right_condition=right_cond))

# ---------------- Step 9 & 10: compute + tabulate ----------------
beam.compute_all()
st.header("6. Results")

for s in beam.spans:
    for pos, g in s.governing.items():
        others = [c for c in g['all_candidates'] if c[0] != g['panel_id']]
        if others:
            st.caption(f"Span {s.index}, {pos}: Panel {g['panel_id']} governs over "
                       f"panel(s) {', '.join(str(o[0]) for o in others)} "
                       f"(Gₖ={g['dead']:.3f} kN/m)")

span_rows = []
for i, s in enumerate(beam.spans):
    RL, RR = s.reactions()
    span_rows.append({
        "Span": f"{i+1}  ({labels[i]} → {labels[i+1]})",
        "L (m)": round(s.length_m, 3),
        "UDL Gₖ (kN/m)": round(s.udl_dead, 2),
        "UDL Qₖ (kN/m)": round(s.udl_live, 2),
        "Left support": labels[i],
        "Gₖ left (kN)": round(RL['dead'], 2),
        "Qₖ left (kN)": round(RL['live'], 2),
        "Right support": labels[i + 1],
        "Gₖ right (kN)": round(RR['dead'], 2),
        "Qₖ right (kN)": round(RR['live'], 2),
    })
st.subheader("Span loads and reactions")
st.table(span_rows)

st.subheader("Total support reactions")
totals = beam.support_reactions()
rows = [{"Support": lbl, "Gₖ (kN)": round(totals[lbl]['dead'], 3),
         "Qₖ (kN)": round(totals[lbl]['live'], 3)} for lbl in labels]
st.table(rows)

# ---------------- Step 11: diagram ----------------
st.header("7. Diagram")
fig, _ = beam.figure()
st.pyplot(fig, width='stretch')

with st.expander("Full text summary"):
    st.code(beam.tabulate())

# ---------------- Step 12: PDF report ----------------
st.header("8. PDF report & saved project")
pdf_name = project.pdf_filename()          # e.g. "Beam F3.pdf"
stem = pdf_name[:-4]
if st.button("Generate PDF report"):
    pdf_path = beam.generate_pdf(pdf_name)
    with open(pdf_path, "rb") as f:
        st.download_button("Download PDF report", f, file_name=pdf_name, mime="application/pdf")

st.subheader("Save this project")
st.caption("Download a link file: opening it later reopens this app with all your inputs filled in, ready to edit.")
_values = _collect_values()
_base = st.text_input("Your app's web address (used inside the link)", value=_detect_base_url(), key="app_base_url",
                      placeholder="https://your-app.streamlit.app")
if _base.strip():
    _url = f"{_base.strip().rstrip('/')}/?p={encode_project_state(_values)}"
    st.download_button(
        "Download project link (.html)",
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={_url}">'
        f'<title>{stem}</title><p><a href="{_url}">Open {stem} in the beam load analysis app</a></p>',
        file_name=f"{stem} (open in app).html", mime="text/html")
    if len(_url) > 6000:
        st.warning("This project is large, so the link may be too long for some browsers.")
else:
    st.info("Type your app's web address above to create a clickable project link.")
