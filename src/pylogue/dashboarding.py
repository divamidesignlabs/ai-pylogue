import html as html_lib
import json

from loguru import logger
from pylogue.embeds import store_html

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from plotly.utils import PlotlyJSONEncoder
except ImportError:
    px = None
    go = None
    make_subplots = None
    PlotlyJSONEncoder = None


def _preview(code: str, limit: int = 240) -> str:
    if not code:
        return ""
    compact = " ".join(code.strip().split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def render_plotly_chart_py(sql_query_runner: callable, sql_query: str, plotly_python: str):
    """Render a Plotly chart using Python code that defines `fig`.

    Prioritizes responsive behavior for chat UIs:
    - fills 100% available width of the chat card
    - adapts to browser resize and mobile breakpoints

    The code runs with access to:
    df (pandas DataFrame), pd (pandas), px (plotly.express),
    go (plotly.graph_objects), make_subplots (plotly.subplots.make_subplots).
    A list-of-dicts alias `data` is also provided for compatibility with
    snippets that start with `pd.DataFrame(data)`.

    Plotly dropdown safety rules (prevents blank charts after selection):
    - For `updatemenus` with `method="update"`, always provide per-trace arrays:
      `x: [series.tolist()]`, `y: [series.tolist()]`, `text: [series.tolist()]`.
    - For `customdata`, pass a 2D payload wrapped per trace:
      `customdata: [df[[...]].to_numpy()]` (never a bare DataFrame).
    - Keep trace type stable across updates, e.g. `fig.update_traces(type="bar", ...)`.
    - Keep `hovertemplate` stable when using `customdata` in dropdown-driven updates.
    - Place dropdowns in a stable area (not over the title), for example:
      `updatemenus=[dict(buttons=buttons, x=0.01, y=1.02, xanchor="left", yanchor="bottom")]`
      and use `fig.update_layout(margin=dict(t=120))`.
      For placement below the chart, use `y=-0.12` and increase `margin.b`.
    - Pylogue auto-normalizes dropdown payloads for common update mistakes,
      so all agents get safer behavior by default.
    - Optional cross-trace click interaction contract (tool-level, agent-agnostic):
      put `layout.meta.pylogue_linked_interaction` with:
      `source_trace` (int), `target_trace` (int), `lookup` (dict),
      and optional `season_menu_index` (int), `default_season` (str),
      `target_title_annotation_index` (int).
      `lookup` keys can be `"<season>||<x_label>"` or `"<x_label>"`.
      Each payload can include `x`, `y`, `text`, `customdata`, `title`.
    """

    try:
        if (
            pd is None
            or go is None
            or px is None
            or make_subplots is None
            or PlotlyJSONEncoder is None
        ):
            return (
                'Missing dependencies. Install with: '
                'pip install "pylogue[dashboard]" plotly'
            )

        local_scope = {
            "pd": pd,
            "px": px,
            "go": go,
            "make_subplots": make_subplots,
        }
        if sql_query_runner is not None and sql_query is not None:
            df = pd.DataFrame(sql_query_runner(sql_query))
            local_scope["df"] = df
            local_scope["data"] = df.to_dict(orient="records")

        try:
            logger.info(
                f"Executed Plotly code: sql_attached={bool(sql_query_runner and sql_query)}, code_preview\n---\n{plotly_python}\n---\n"
            )
            exec(plotly_python, local_scope)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly code execution failed: sql_attached={}, code_preview={!r}",
                bool(sql_query_runner and sql_query),
                _preview(plotly_python),
            )
            return f"Error executing Plotly code: {exc}"

        fig = local_scope.get("fig")
        if fig is None or not hasattr(fig, "to_plotly_json"):
            return "Error: Plotly code must define a `fig` variable."

        try:
            fig_json = fig.to_plotly_json()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly serialization failed: fig_type={}, code_preview={!r}",
                fig.__class__.__name__ if fig is not None else "unknown",
                _preview(plotly_python),
            )
            return f"Error serializing Plotly figure: {exc}"

        layout = fig_json.get("layout") or {}
        user_height = layout.get("height")
        has_explicit_height = isinstance(user_height, (int, float))
        default_height = int(user_height) if has_explicit_height else 420

        if not has_explicit_height:
            # Let Plotly autosize width while we manage a mobile-friendly height.
            fig_json.setdefault("layout", {})
            fig_json["layout"]["autosize"] = True
            fig_json["layout"].pop("width", None)

        fig_payload = json.dumps(fig_json, cls=PlotlyJSONEncoder)
        script_html = (
            "<div id='plot-wrap' style='width:100%;max-width:100%;height:100%;margin:0;'>"
            "<div id='plot-root' style='width:100%;height:100%;'></div>"
            "</div>"
            "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>"
            "<script>"
            f"const fig={fig_payload};"
            f"const explicitHeight={'true' if has_explicit_height else 'false'};"
            f"const defaultHeight={default_height};"
            "const gd=document.getElementById('plot-root');"
            "const TRACE_KEYS=['x','y','text','customdata'];"
            "function normalizePerTraceValue(value, traceCount){"
            "if(value===undefined||value===null) return value;"
            "if(!Array.isArray(value)) return [value];"
            "if(traceCount===1){"
            "if(value.length===0) return [[]];"
            "if(Array.isArray(value[0])) return value;"
            "return [value];"
            "}"
            "if(value.length===traceCount && value.every((item)=>Array.isArray(item)||item===null)) return value;"
            "if(!Array.isArray(value[0])) return [value];"
            "return value;"
            "}"
            "function stripFragileAnnotationKeys(obj){"
            "if(!obj||typeof obj!=='object') return;"
            "for(const key of Object.keys(obj)){"
            "if(key.startsWith('annotations[')&&key.endsWith('].text')) delete obj[key];"
            "}"
            "}"
            "function normalizeUpdateMenus(){"
            "const layout=fig.layout||{};"
            "const menus=layout.updatemenus||[];"
            "const traceCount=(fig.data||[]).length||1;"
            "for(const menu of menus){"
            "const buttons=(menu&&menu.buttons)||[];"
            "for(const btn of buttons){"
            "if(!btn||!Array.isArray(btn.args)||btn.args.length===0) continue;"
            "if(String(btn.method||'').toLowerCase()!=='update') continue;"
            "const dataArgs=btn.args[0];"
            "if(dataArgs&&typeof dataArgs==='object'){"
            "for(const key of TRACE_KEYS){"
            "if(key in dataArgs){"
            "dataArgs[key]=normalizePerTraceValue(dataArgs[key], traceCount);"
            "}"
            "}"
            "stripFragileAnnotationKeys(dataArgs);"
            "}"
            "const layoutArgs=btn.args.length>1?btn.args[1]:null;"
            "if(layoutArgs&&typeof layoutArgs==='object'){"
            "stripFragileAnnotationKeys(layoutArgs);"
            "}"
            "}"
            "}"
            "}"
            "function setupLinkedInteraction(){"
            "const meta=((fig.layout||{}).meta||{}).pylogue_linked_interaction;"
            "if(!meta||typeof meta!=='object') return;"
            "const sourceTrace=Number.isInteger(meta.source_trace)?meta.source_trace:0;"
            "const targetTrace=Number.isInteger(meta.target_trace)?meta.target_trace:1;"
            "const seasonMenuIndex=Number.isInteger(meta.season_menu_index)?meta.season_menu_index:0;"
            "const lookup=(meta.lookup&&typeof meta.lookup==='object')?meta.lookup:{};"
            "const defaultSeason=meta.default_season==null?'':String(meta.default_season);"
            "function normalizeLinkedSeries(value){"
            "if(Array.isArray(value) && value.length===1 && Array.isArray(value[0])){"
            "return value[0];"
            "}"
            "return value;"
            "}"
            "function activeSeason(){"
            "try{"
            "const menus=(gd.layout&&gd.layout.updatemenus)||[];"
            "const menu=menus[seasonMenuIndex];"
            "if(!menu||!Array.isArray(menu.buttons)) return defaultSeason;"
            "const active=Number.isInteger(menu.active)?menu.active:0;"
            "const btn=menu.buttons[active];"
            "if(!btn||btn.label==null) return defaultSeason;"
            "return String(btn.label);"
            "}catch(_err){return defaultSeason;}"
            "}"
            "gd.on('plotly_click', function(eventData){"
            "const point=eventData&&eventData.points&&eventData.points[0];"
            "if(!point||point.curveNumber!==sourceTrace) return;"
            "const label=String(point.x);"
            "const season=activeSeason();"
            "const combinedKey=season+'||'+label;"
            "const payload=lookup[combinedKey]||lookup[label];"
            "if(!payload||typeof payload!=='object') return;"
            "const update={};"
            "for(const key of TRACE_KEYS){"
            "if(payload[key]!==undefined){"
            "const val=(key==='customdata')?payload[key]:normalizeLinkedSeries(payload[key]);"
            "update[key]=[val];"
            "}"
            "}"
            "if(Object.keys(update).length===0) return;"
            "try{"
            "const fullData=gd._fullData||[];"
            "const target=fullData[targetTrace]||{};"
            "const yRef=String(target.yaxis||'y');"
            "const yLayoutKey=(yRef==='y')?'yaxis':'yaxis'+yRef.slice(1);"
            "const yVals=payload.y;"
            "if(Array.isArray(yVals) && yVals.length>0 && typeof yVals[0]==='string'){"
            "const patch={};"
            "patch[yLayoutKey+'.type']='category';"
            "Plotly.relayout(gd, patch);"
            "}"
            "}catch(_err){}"
            "Plotly.restyle(gd, update, [targetTrace]);"
            "if(payload.title){"
            "try{"
            "const anns=(gd.layout&&gd.layout.annotations)||[];"
            "const idx=Number.isInteger(meta.target_title_annotation_index)?meta.target_title_annotation_index:(anns.length>1?1:0);"
            "if(anns.length && idx>=0 && idx<anns.length){"
            "const relayoutPatch={};"
            "relayoutPatch['annotations['+idx+'].text']=String(payload.title);"
            "Plotly.relayout(gd, relayoutPatch);"
            "}else{"
            "Plotly.relayout(gd, {title:String(payload.title)});"
            "}"
            "}catch(_err){}"
            "}"
            "});"
            "}"
            "function mobileHeight(){"
            "if(explicitHeight) return defaultHeight;"
            "const frameH=(window.frameElement&&window.frameElement.clientHeight)||0;"
            "const viewH=window.innerHeight||0;"
            "const h=Math.max(frameH, viewH);"
            "if(h>0) return Math.max(280, Math.round(h-8));"
            "const w=Math.max(280, Math.min(window.innerWidth||1024, 1400));"
            "return Math.max(280, Math.round(w*0.6));"
            "}"
            "function render(){"
            "normalizeUpdateMenus();"
            "fig.layout=fig.layout||{};"
            "fig.layout.autosize=true;"
            "fig.layout.width=null;"
            "fig.layout.height=mobileHeight();"
            "if(window.frameElement){"
            "window.frameElement.style.height=fig.layout.height+'px';"
            "window.frameElement.height=String(fig.layout.height);"
            "}"
            "Plotly.react(gd, fig.data||[], fig.layout, {responsive:true, displaylogo:false});"
            "}"
            "render();"
            "setupLinkedInteraction();"
            "const ro=new ResizeObserver(()=>{"
            "render();"
            "try{Plotly.Plots.resize(gd);}catch(e){}"
            "});"
            "ro.observe(document.body);"
            "window.addEventListener('resize', ()=>{"
            "render();"
            "try{Plotly.Plots.resize(gd);}catch(e){}"
            "});"
            "</script>"
        )

        srcdoc = (
            "<!doctype html><html><head><meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<style>html,body{margin:0;padding:0;height:100%;background:#fff;overflow:hidden;}"
            "#plot-wrap,#plot-root{width:100%;max-width:100%;height:100%;}</style>"
            "</head><body>"
            f"{script_html}"
            "</body></html>"
        )
        escaped_srcdoc = html_lib.escape(srcdoc, quote=True)
        iframe_html = (
            '<iframe '
            f'srcdoc="{escaped_srcdoc}" '
            f'height="{default_height}" '
            "style=\"width:100%;max-width:100%;height:"
            f"{default_height}px;border:0;display:block;\" "
            'title="Plotly Chart"></iframe>'
        )
        html_id = store_html(iframe_html)
        return {"_pylogue_html_id": html_id, "message": "Plotly chart rendered."}
    except Exception as e:
        logger.exception(
            "Unhandled error in render_plotly_chart_py: sql_attached={}, code_preview={!r}",
            bool(sql_query_runner and sql_query),
            _preview(plotly_python),
        )
        return f"Error in render_plotly_chart_py: {e}"
