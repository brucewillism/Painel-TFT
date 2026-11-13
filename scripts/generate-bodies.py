#!/usr/bin/env python3
"""Gera as silhuetas vetoriais (lado e topo) dos 6 tipos de carroceria."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "static" / "img" / "bodies"


def defs(prefix: str, *, top: bool = False) -> str:
    if top:
        return f'''  <defs>
    <linearGradient id="{prefix}-topSheen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#000" stop-opacity="0.28"/>
      <stop offset="40%" stop-color="#fff" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.32"/>
    </linearGradient>
    <linearGradient id="{prefix}-glassTop" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6a8aaa" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#1a2838" stop-opacity="0.85"/>
    </linearGradient>
  </defs>'''
    return f'''  <defs>
    <linearGradient id="{prefix}-sheen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fff" stop-opacity="0.28"/>
      <stop offset="35%" stop-color="#fff" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.42"/>
    </linearGradient>
    <linearGradient id="{prefix}-glass" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#9eb4c8" stop-opacity="0.55"/>
      <stop offset="45%" stop-color="#2a3a4a" stop-opacity="0.72"/>
      <stop offset="100%" stop-color="#0a1218" stop-opacity="0.92"/>
    </linearGradient>
    <linearGradient id="{prefix}-glow" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="var(--accent, #e10600)" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="var(--accent, #e10600)" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="{prefix}-rim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#d8d8de"/>
      <stop offset="100%" stop-color="#6a6a72"/>
    </linearGradient>
    <radialGradient id="{prefix}-tire" cx="50%" cy="45%" r="55%">
      <stop offset="70%" stop-color="#1a1a1e"/>
      <stop offset="100%" stop-color="#050506"/>
    </radialGradient>
    <clipPath id="{prefix}-bodyClip"><path d="__CLIP__"/></clipPath>
  </defs>'''


def wheel(prefix: str, cx: float, cy: float, r: float, which: str) -> str:
    """Roda grande, perfil baixo, 10 raios — visual de aro 18"."""
    import math
    tire_in = r * 0.84
    rim = r * 0.80
    lip = r * 0.70
    hub = r * 0.15
    spokes = []
    n = 10
    for i in range(n):
        a = i * 2 * math.pi / n - math.pi / 2
        half = math.pi / n * 0.32
        ao, ai = a - half, a + half
        x0 = hub * 1.2 * math.cos(a)
        y0 = hub * 1.2 * math.sin(a)
        x1 = lip * 0.98 * math.cos(ao)
        y1 = lip * 0.98 * math.sin(ao)
        x2 = lip * 0.98 * math.cos(ai)
        y2 = lip * 0.98 * math.sin(ai)
        spokes.append(
            f'<path d="M{x0:.2f},{y0:.2f} L{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f} Z"/>'
        )
    sw = max(1.8, r * 0.045)
    return f"""  <g class="wheel wheel-{which}" transform="translate({cx:.1f},{cy:.1f})">
    <circle r="{r:.1f}" fill="url(#{prefix}-tire)"/>
    <circle r="{tire_in:.1f}" fill="#141418"/>
    <circle r="{rim:.1f}" fill="none" stroke="#7a7a84" stroke-width="{max(1.3, r*0.03):.1f}"/>
    <circle r="{lip:.1f}" fill="#26262e" stroke="url(#{prefix}-rim)" stroke-width="{sw:.1f}"/>
    <g class="spokes" fill="#d4d4dc" stroke="#8a8a94" stroke-width="0.35">
      {"".join(spokes)}
    </g>
    <circle r="{hub:.1f}" fill="#1a1a20" stroke="#d0d0d8" stroke-width="1.5"/>
    <circle r="{hub * 0.42:.1f}" fill="#3a3a44"/>
    <circle r="{r:.1f}" fill="none" stroke="#0a0a0c" stroke-width="1.1"/>
  </g>"""


def arch_pair(fx, rx, cy, r, rocker, gap=5) -> str:
    """Trecho do fundo do body, da direita (traseira) para a esquerda, com dois arcos justos."""
    ar = r + 3
    return (
        f"L{rx + r + gap:.1f},{rocker:.1f} "
        f"A{ar:.1f},{ar:.1f} 0 0 0 {rx - r - gap:.1f},{rocker:.1f} "
        f"L{fx + r + gap:.1f},{rocker:.1f} "
        f"A{ar:.1f},{ar:.1f} 0 0 0 {fx - r - gap:.1f},{rocker:.1f}"
    )


def side_svg(prefix, label, body_d, extras: str, fx, rx, cy, r, clip_d=None) -> str:
    clip = clip_d or body_d
    head = defs(prefix).replace("__CLIP__", clip)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 340" width="1000" height="340" aria-label="{label}, vista lateral original">
{head}
  <ellipse class="underglow" cx="500" cy="300" rx="360" ry="18" fill="url(#{prefix}-glow)"/>
  <ellipse cx="500" cy="304" rx="340" ry="11" fill="#000" opacity="0.45"/>

  <g class="car-body">
    <path class="paint" d="{body_d}" fill="var(--car-paint, #b1121a)" stroke="#140404" stroke-width="1.5" stroke-linejoin="round"/>
    <path clip-path="url(#{prefix}-bodyClip)" d="M40,30 H960 V280 H40 Z" fill="url(#{prefix}-sheen)" opacity="0.95"/>
{extras}
  </g>

{wheel(prefix, fx, cy, r, "front")}
{wheel(prefix, rx, cy, r, "rear")}
</svg>
"""


# ── Sedã moderno — teto baixo, A-pilar rápido, fastback, cintura em cunha, aros grandes.
SEDAN_BODY = (
    "M74,210 C66,194 82,166 118,156 "
    "C190,146 260,144 328,142 "
    "C358,142 390,122 420,102 "
    "C450,84 478,80 520,80 "
    "C590,78 655,82 705,96 "
    "C745,108 775,128 805,146 "
    "C845,148 888,152 924,156 "
    "C958,160 974,178 968,210 "
    "L958,240 "
    + arch_pair(200, 800, 248, 68, 240, 5) +
    " L102,240 C86,240 78,216 76,198 Z"
)

SEDAN_EXTRAS = """
    <path d="M78,214 L130,202 L210,202 L204,230 L96,232 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M114,166 L186,160 L190,176 L118,180 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M328,142 C358,142 390,122 420,102 C450,84 478,80 520,80 C590,78 655,82 705,96 C745,108 775,128 805,146 L786,140 C756,122 728,106 694,98 C640,88 580,84 524,86 C484,88 454,96 424,114 C390,134 356,142 334,142 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M338,142 C372,140 400,118 430,100 C456,86 486,82 520,82 L540,82 L540,146 L338,146 Z" fill="url(#sedan-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M554,82 L655,86 L655,140 L554,146 Z" fill="url(#sedan-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass win-rear" d="M668,86 L710,94 L792,138 L668,140 Z" fill="url(#sedan-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M812,146 L912,156 L902,174 L812,166 Z" fill="url(#sedan-glass)" stroke="#1a2028" stroke-width="0.85" opacity="0.9"/>
    <path d="M360,108 L430,86 L440,118 L376,132 Z" fill="#fff" opacity="0.13"/>
    <path d="M540,80 L540,148" stroke="#1a0a0a" stroke-width="7.2"/>
    <path d="M655,84 L655,142" stroke="#1a0a0a" stroke-width="6.2"/>
    <path d="M710,92 L792,140" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M210,148 C360,140 560,132 800,146" fill="none" stroke="#fff" stroke-opacity="0.16" stroke-width="1.4"/>
    <path d="M186,186 C360,170 640,164 910,182" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M540,148 L532,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <path d="M655,142 L655,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <rect x="590" y="160" width="22" height="5" rx="2" fill="#2a2a30"/>
    <rect x="700" y="154" width="22" height="5" rx="2" fill="#2a2a30"/>
    <path d="M348,134 L398,116 L408,136 L358,152 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M384,120 L402,116 L406,132 L390,134 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M300,228 L720,228 L734,240 L286,240 Z" fill="#0a0a0c" opacity="0.85"/>
    <path class="headlight" d="M88,176 L166,166 L170,180 L94,194 Z" fill="#e8eef8"/>
    <path d="M92,178 L166,168 L168,174 L94,186 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M88,176 L8,150 L8,210 L94,196 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M108,184 L140,178 L140,190 L108,196 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M914,156 L962,164 L956,184 L908,174 Z" fill="#4a0000"/>
    <path d="M918,160 L958,166 L956,172 L916,166 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M916,158 L960,166 L954,180 L910,172 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M920,172 L950,178 L948,186 L918,180 Z" fill="#ffb000" opacity="0"/>
"""

# Hatch — teto segue até uma traseira tipo kamm, spoiler no fio do teto.
HATCH_BODY = (
    "M76,210 C68,194 84,166 120,156 "
    "C190,146 260,144 328,142 "
    "C358,142 390,120 420,100 "
    "C450,82 480,78 524,78 "
    "C610,76 700,84 760,104 "
    "C810,118 860,146 916,174 "
    "C944,186 960,202 954,222 "
    "L944,240 "
    + arch_pair(200, 792, 248, 68, 240, 5) +
    " L104,240 C88,240 80,216 78,198 Z"
)

HATCH_EXTRAS = """
    <path d="M80,214 L130,202 L210,202 L204,230 L98,232 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M116,166 L186,160 L190,176 L120,180 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M328,142 C358,142 390,120 420,100 C450,82 480,78 524,78 C610,76 700,84 760,104 C810,118 860,146 916,174 L896,168 C850,144 804,120 752,108 C690,92 610,84 534,84 C490,86 458,94 426,114 C392,132 358,142 334,142 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M338,142 C372,140 400,116 430,98 C456,84 488,80 524,80 L544,80 L544,146 L338,146 Z" fill="url(#hatch-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M558,80 L658,84 L658,140 L558,146 Z" fill="url(#hatch-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass win-rear" d="M672,84 L748,98 L884,166 L672,140 Z" fill="url(#hatch-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M894,168 L938,182 L926,204 L890,194 Z" fill="url(#hatch-glass)" stroke="#1a2028" stroke-width="0.85"/>
    <path d="M360,108 L430,84 L440,118 L376,132 Z" fill="#fff" opacity="0.13"/>
    <path d="M544,78 L544,148" stroke="#1a0a0a" stroke-width="7.2"/>
    <path d="M658,82 L658,142" stroke="#1a0a0a" stroke-width="6.2"/>
    <path d="M748,96 L884,166" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M868,150 L916,174 L906,178 L862,156 Z" fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.6"/>
    <path d="M210,148 C360,140 600,134 880,166" fill="none" stroke="#fff" stroke-opacity="0.15" stroke-width="1.3"/>
    <path d="M186,186 C360,170 640,166 880,190" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M544,148 L536,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <path d="M658,142 L658,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <rect x="592" y="160" width="22" height="5" rx="2" fill="#2a2a30"/>
    <rect x="710" y="154" width="22" height="5" rx="2" fill="#2a2a30"/>
    <path d="M348,134 L398,116 L408,136 L358,152 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M384,120 L402,116 L406,132 L390,134 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M300,228 L720,228 L734,240 L286,240 Z" fill="#0a0a0c" opacity="0.85"/>
    <path class="headlight" d="M90,176 L168,166 L172,180 L96,194 Z" fill="#e8eef8"/>
    <path d="M94,178 L168,168 L170,174 L96,186 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M90,176 L10,150 L10,210 L96,196 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M110,184 L142,178 L142,190 L110,196 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M900,172 L948,186 L938,210 L888,196 Z" fill="#4a0000"/>
    <path d="M904,176 L944,188 L940,196 L900,182 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M902,174 L946,188 L936,206 L890,194 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M906,188 L934,198 L930,208 L904,198 Z" fill="#ffb000" opacity="0"/>
"""

# SUV / crossover — mais alto, teto longo com queda suave, barras, D-pilar mais em pé.
SUV_BODY = (
    "M72,198 C64,182 80,148 118,138 "
    "C186,128 258,126 328,124 "
    "C354,124 378,104 400,84 "
    "C422,66 452,60 500,58 "
    "C600,54 710,58 790,78 "
    "C830,90 870,114 910,136 "
    "C938,150 960,160 966,186 "
    "C970,204 962,216 952,220 "
    + arch_pair(205, 800, 252, 70, 220, 5) +
    " L106,220 C88,220 76,202 74,186 Z"
)

SUV_EXTRAS = """
    <path d="M76,200 L132,188 L214,188 L208,214 L96,218 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M116,150 L192,144 L196,162 L120,166 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M328,124 C354,124 378,104 400,84 C422,66 452,60 500,58 C600,54 710,58 790,78 C830,90 870,114 910,136 L890,132 C850,112 814,94 780,86 C710,68 600,64 510,66 C462,68 432,78 406,96 C378,116 350,124 334,124 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M338,124 C368,122 390,100 416,82 C438,68 466,62 500,60 L524,60 L524,128 L338,128 Z" fill="url(#suv-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M538,60 L668,64 L668,124 L538,128 Z" fill="url(#suv-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass win-rear" d="M682,64 L778,80 L888,132 L682,124 Z" fill="url(#suv-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M898,134 L942,152 L930,176 L894,160 Z" fill="url(#suv-glass)" stroke="#1a2028" stroke-width="0.85"/>
    <path d="M356,92 L420,66 L430,104 L372,118 Z" fill="#fff" opacity="0.12"/>
    <path d="M524,58 L524,130" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M668,62 L668,126" stroke="#1a0a0a" stroke-width="6.5"/>
    <path d="M778,78 L888,132" stroke="#1a0a0a" stroke-width="7.5"/>
    <rect x="460" y="46" width="260" height="5" rx="2" fill="#1a1a1e"/>
    <rect x="478" y="42" width="7" height="14" rx="1" fill="#2a2a30"/>
    <rect x="696" y="42" width="7" height="14" rx="1" fill="#2a2a30"/>
    <path d="M214,128 C360,120 600,116 880,136" fill="none" stroke="#fff" stroke-opacity="0.14" stroke-width="1.3"/>
    <path d="M176,174 C360,158 640,154 900,176" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M524,128 L516,220" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <path d="M668,124 L668,220" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <rect x="582" y="142" width="22" height="5" rx="2" fill="#2a2a30"/>
    <rect x="724" y="138" width="22" height="5" rx="2" fill="#2a2a30"/>
    <path d="M346,118 L392,100 L402,120 L356,136 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M378,104 L396,100 L400,116 L384,118 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M300,208 L720,208 L734,220 L286,220 Z" fill="#0a0a0c" opacity="0.85"/>
    <path d="M110,198 L910,198 L920,220 L100,220 Z" fill="#1a1a1e" opacity="0.42"/>
    <path class="headlight" d="M88,156 L170,144 L176,160 L96,176 Z" fill="#e8eef8"/>
    <path d="M92,158 L170,146 L172,154 L96,166 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M88,156 L10,128 L10,200 L96,178 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M110,164 L144,156 L144,168 L110,176 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M918,144 L964,158 L956,184 L910,168 Z" fill="#4a0000"/>
    <path d="M922,148 L960,160 L956,168 L918,154 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M920,146 L962,160 L954,180 L912,166 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M924,164 L952,174 L948,184 L922,174 Z" fill="#ffb000" opacity="0"/>
"""

# Picape moderna — cabine curta, caçamba e tampa mais quadradas, aros grandes.
PICKUP_BODY = (
    "M74,200 C66,184 82,152 118,142 "
    "C184,132 254,130 322,128 "
    "C348,128 372,108 394,86 "
    "C416,68 444,62 488,62 "
    "C545,60 590,66 618,90 "
    "C636,106 646,122 650,132 "
    "L650,146 L918,148 "
    "L932,148 L936,156 L928,220 "
    + arch_pair(200, 805, 252, 70, 220, 5) +
    " L104,220 C88,220 78,204 76,188 Z"
)

PICKUP_EXTRAS = """
    <path d="M78,202 L132,190 L214,190 L208,214 L96,218 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M116,152 L190,146 L194,164 L120,168 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M322,128 C348,128 372,108 394,86 C416,68 444,62 488,62 C545,60 590,66 618,90 C636,106 646,122 650,132 L628,132 C616,116 600,98 570,86 C530,72 470,70 430,72 C400,74 380,84 360,100 C340,118 326,128 328,128 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M332,128 C362,126 384,104 410,84 C432,70 458,64 488,64 L512,64 L512,132 L332,132 Z" fill="url(#pickup-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M526,64 L592,70 L636,132 L526,132 Z" fill="url(#pickup-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M636,132 L650,132 L650,152 L628,152 Z" fill="url(#pickup-glass)" stroke="#1a2028" stroke-width="0.8" opacity="0.85"/>
    <path d="M350,98 L412,70 L422,108 L366,122 Z" fill="#fff" opacity="0.12"/>
    <path d="M512,62 L512,134" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M592,68 L636,132" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M650,132 L650,220" stroke="#1a0a0a" stroke-width="3.2"/>
    <path d="M650,146 L918,148" fill="none" stroke="#fff" stroke-opacity="0.16" stroke-width="1.7"/>
    <path d="M662,150 L908,152 L904,214 L658,212 Z" fill="#16161c" opacity="0.30"/>
    <path d="M908,148 L932,148 L928,220 L904,220 Z" fill="#0e0e12" opacity="0.72"/>
    <path d="M214,132 C360,124 520,122 640,132" fill="none" stroke="#fff" stroke-opacity="0.14" stroke-width="1.3"/>
    <path d="M176,176 C340,162 560,160 900,176" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M512,132 L504,220" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <rect x="554" y="148" width="22" height="5" rx="2" fill="#2a2a30"/>
    <path d="M338,122 L386,104 L396,124 L348,140 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M372,108 L390,104 L394,120 L378,122 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M300,208 L910,208 L922,220 L286,220 Z" fill="#0a0a0c" opacity="0.85"/>
    <path d="M108,202 L910,202 L920,220 L98,220 Z" fill="#1a1a1e" opacity="0.4"/>
    <path class="headlight" d="M88,158 L168,146 L174,162 L96,178 Z" fill="#e8eef8"/>
    <path d="M92,160 L168,148 L170,156 L96,168 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M88,158 L10,130 L10,200 L96,180 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M110,166 L144,158 L144,170 L110,178 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M920,158 L960,166 L954,206 L916,198 Z" fill="#4a0000"/>
    <path d="M924,164 L956,170 L954,178 L922,172 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M920,160 L958,168 L952,202 L916,194 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M924,184 L950,190 L948,200 L922,194 Z" fill="#ffb000" opacity="0"/>
"""

# Cupê — capô longo, teto muito baixo, fastback forte, 2 portas, uma janela longa.
COUPE_BODY = (
    "M72,210 C64,196 80,166 118,154 "
    "C200,144 280,142 360,140 "
    "C396,140 432,118 466,96 "
    "C500,76 536,74 584,76 "
    "C660,80 735,96 790,122 "
    "C830,140 870,150 922,156 "
    "C954,160 972,178 966,210 "
    "L956,240 "
    + arch_pair(210, 800, 248, 70, 240, 5) +
    " L104,240 C86,240 76,218 74,200 Z"
)

COUPE_EXTRAS = """
    <path d="M76,214 L134,202 L220,202 L214,230 L96,232 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M118,164 L210,156 L214,174 L122,178 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M360,140 C396,140 432,118 466,96 C500,76 536,74 584,76 C660,80 735,96 790,122 C830,140 870,150 922,156 L900,152 C850,144 810,132 774,116 C720,94 650,84 592,82 C548,82 514,88 480,106 C440,128 400,140 368,140 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M370,140 C408,138 440,114 476,94 C506,80 542,76 584,78 L604,78 L604,146 L370,146 Z" fill="url(#coupe-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M618,78 L740,100 L888,152 L618,146 Z" fill="url(#coupe-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M896,152 L940,158 L930,176 L896,170 Z" fill="url(#coupe-glass)" stroke="#1a2028" stroke-width="0.85" opacity="0.9"/>
    <path d="M400,110 L490,82 L502,116 L420,134 Z" fill="#fff" opacity="0.13"/>
    <path d="M604,76 L604,148" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M740,98 L888,152" stroke="#1a0a0a" stroke-width="7.5"/>
    <path d="M230,146 C420,136 680,132 910,154" fill="none" stroke="#fff" stroke-opacity="0.16" stroke-width="1.4"/>
    <path d="M186,186 C400,168 720,164 910,184" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M604,146 L592,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.35"/>
    <rect x="670" y="160" width="24" height="5" rx="2" fill="#2a2a30"/>
    <path d="M382,132 L440,110 L452,132 L394,152 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M426,114 L446,108 L452,126 L434,130 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M310,228 L730,228 L744,240 L296,240 Z" fill="#0a0a0c" opacity="0.85"/>
    <path class="headlight" d="M86,176 L176,164 L182,178 L94,194 Z" fill="#e8eef8"/>
    <path d="M90,178 L176,166 L178,172 L94,186 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M86,176 L6,150 L6,210 L94,196 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M110,184 L146,176 L146,188 L110,196 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M916,156 L964,164 L958,184 L910,174 Z" fill="#4a0000"/>
    <path d="M920,160 L960,166 L958,172 L918,166 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M918,158 L962,166 L956,180 L912,172 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M922,172 L952,178 L950,186 L920,180 Z" fill="#ffb000" opacity="0"/>
"""

# Perua / sport wagon — frente de sedã, teto longo e baixo, pilar D inclinado.
WAGON_BODY = (
    "M74,210 C66,194 82,166 118,156 "
    "C190,146 260,144 328,142 "
    "C358,142 390,120 420,100 "
    "C450,82 480,78 524,78 "
    "C620,74 730,78 810,94 "
    "C860,104 905,128 936,156 "
    "C958,170 972,190 966,216 "
    "L956,240 "
    + arch_pair(200, 800, 248, 68, 240, 5) +
    " L102,240 C86,240 78,216 76,198 Z"
)

WAGON_EXTRAS = """
    <path d="M78,214 L130,202 L210,202 L204,230 L96,232 Z" fill="#0c0c10" opacity="0.94"/>
    <path d="M114,166 L186,160 L190,176 L118,180 Z" fill="#16161c"/>
    <path class="paint greenhouse" d="M328,142 C358,142 390,120 420,100 C450,82 480,78 524,78 C620,74 730,78 810,94 C860,104 905,128 936,156 L916,150 C872,126 828,108 800,100 C730,86 620,82 534,84 C490,86 458,94 426,114 C392,132 358,142 334,142 Z"
          fill="var(--car-paint, #b1121a)" stroke="#1a0808" stroke-width="0.7"/>
    <path class="glass windshield" d="M338,142 C372,140 400,116 430,98 C456,84 488,80 524,80 L544,80 L544,146 L338,146 Z" fill="url(#wagon-glass)" stroke="#1a2028" stroke-width="1.15"/>
    <path class="glass win-front" d="M558,80 L658,84 L658,140 L558,146 Z" fill="url(#wagon-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass win-rear" d="M672,84 L800,96 L916,150 L672,140 Z" fill="url(#wagon-glass)" stroke="#1a2028" stroke-width="1.1"/>
    <path class="glass rear-glass" d="M922,152 L952,168 L940,194 L916,180 Z" fill="url(#wagon-glass)" stroke="#1a2028" stroke-width="0.85"/>
    <path d="M360,108 L430,84 L440,118 L376,132 Z" fill="#fff" opacity="0.13"/>
    <path d="M544,78 L544,148" stroke="#1a0a0a" stroke-width="7.2"/>
    <path d="M658,82 L658,142" stroke="#1a0a0a" stroke-width="6.2"/>
    <path d="M800,94 L916,150" stroke="#1a0a0a" stroke-width="7.5"/>
    <rect x="520" y="66" width="230" height="4" rx="2" fill="#1a1a1e"/>
    <rect x="538" y="62" width="6" height="12" rx="1" fill="#2a2a30"/>
    <rect x="714" y="62" width="6" height="12" rx="1" fill="#2a2a30"/>
    <path d="M210,148 C360,140 640,134 910,154" fill="none" stroke="#fff" stroke-opacity="0.15" stroke-width="1.3"/>
    <path d="M186,186 C360,170 640,166 900,186" fill="none" stroke="#000" stroke-opacity="0.28" stroke-width="1.25"/>
    <path d="M544,148 L536,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <path d="M658,142 L658,240" stroke="#000" stroke-opacity="0.38" stroke-width="1.3"/>
    <rect x="592" y="160" width="22" height="5" rx="2" fill="#2a2a30"/>
    <rect x="730" y="154" width="22" height="5" rx="2" fill="#2a2a30"/>
    <path d="M348,134 L398,116 L408,136 L358,152 Z" fill="#16161a" stroke="#2a0a0a" stroke-width="0.8"/>
    <path d="M384,120 L402,116 L406,132 L390,134 Z" fill="#9aa4b0" opacity="0.55"/>
    <path d="M300,228 L720,228 L734,240 L286,240 Z" fill="#0a0a0c" opacity="0.85"/>
    <path class="headlight" d="M88,176 L166,166 L170,180 L94,194 Z" fill="#e8eef8"/>
    <path d="M92,178 L166,168 L168,174 L94,186 Z" fill="#fff" opacity="0.85"/>
    <path class="headlight-beam" d="M88,176 L8,150 L8,210 L94,196 Z" fill="#fff5e0" opacity="0"/>
    <path class="turn-fl" d="M108,184 L140,178 L140,190 L108,196 Z" fill="#ffb000" opacity="0"/>
    <path class="taillight" d="M918,154 L966,170 L958,196 L910,180 Z" fill="#4a0000"/>
    <path d="M922,158 L962,172 L958,180 L916,166 Z" fill="#ff3a3a" opacity="0.55"/>
    <path class="brake-light" d="M920,156 L964,172 L956,192 L912,178 Z" fill="#ff1a1a" opacity="0"/>
    <path class="turn-rl" d="M924,174 L954,186 L950,196 L922,184 Z" fill="#ffb000" opacity="0"/>
"""



def top_svg(prefix, label, body_d, extras) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 520" width="240" height="520" aria-label="{label}, vista de cima original">
{defs(prefix, top=True)}
  <path class="paint" d="{body_d}" fill="var(--car-paint, #b1121a)" stroke="#140404" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="{body_d}" fill="url(#{prefix}-topSheen)"/>
{extras}
</svg>
'''


def zones(prefix, trans_label="câmbio"):
    # generic alert zones; trans may be CVT or gearbox
    return f'''
  <g id="zone-engine" class="zone zone-engine">
    <rect x="78" y="86" width="84" height="58" rx="5" fill="#e10600" fill-opacity="0.12" stroke="#e10600" stroke-opacity="0.4"/>
  </g>
  <g id="zone-battery" class="zone zone-battery">
    <rect x="86" y="98" width="24" height="18" rx="2" fill="#e10600" fill-opacity="0.12" stroke="#e10600" stroke-opacity="0.4"/>
  </g>
  <g id="zone-cvt" class="zone zone-cvt zone-trans">
    <rect x="96" y="210" width="48" height="30" rx="4" fill="#e10600" fill-opacity="0.12" stroke="#e10600" stroke-opacity="0.4"/>
  </g>'''


# sedan top — 3 boxes, tapering nose, distinct trunk
SEDAN_TOP = (
    "M78,52 C66,58 56,80 54,110 "
    "L50,170 L48,250 L50,330 L56,390 "
    "C60,422 78,444 120,452 "
    "C162,444 180,422 184,390 "
    "L190,330 L192,250 L190,170 "
    "L186,110 C184,80 174,58 162,52 "
    "C148,38 92,38 78,52 Z"
)
SEDAN_TOP_EX = f'''
  <path d="M68,158 L172,158 L162,250 L78,250 Z" fill="url(#sedan-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M78,252 L162,252 L154,332 L86,332 Z" fill="#1a1010" opacity="0.55"/>
  <path d="M86,334 L154,334 L146,378 L94,378 Z" fill="url(#sedan-glassTop)" opacity="0.85" stroke="#2a3844" stroke-width="0.7"/>
  <path d="M96,56 L120,74 L144,56" fill="none" stroke="#111" stroke-width="2"/>
  <path d="M100,62 L120,76 L140,62" fill="#111" opacity="0.75"/>
  {zones("sedan")}
  <rect class="headlight-t" x="56" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="160" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="66" y="418" width="26" height="11" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="148" y="418" width="26" height="11" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="52" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="175" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="32" y="154" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="190" y="154" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="38" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="191" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="38" y="308" width="11" height="40" rx="3" fill="#111"/>
  <rect x="191" y="308" width="11" height="40" rx="3" fill="#111"/>
  <!-- linhas de porta -->
  <path d="M68,200 L172,200 M68,250 L172,250" fill="none" stroke="#000" stroke-opacity="0.25" stroke-width="0.8"/>
'''

HATCH_TOP = (
    "M80,54 C68,60 58,82 56,112 "
    "L52,175 L50,255 L54,350 L62,410 "
    "C68,436 90,450 120,454 "
    "C150,450 172,436 178,410 "
    "L186,350 L190,255 L188,175 "
    "L184,112 C182,82 172,60 160,54 "
    "C148,40 92,40 80,54 Z"
)
HATCH_TOP_EX = f'''
  <path d="M70,160 L170,160 L162,260 L78,260 Z" fill="url(#hatch-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M78,262 L162,262 L150,400 L90,400 Z" fill="url(#hatch-glassTop)" opacity="0.8" stroke="#2a3844" stroke-width="0.7"/>
  <path d="M98,58 L120,76 L142,58" fill="none" stroke="#111" stroke-width="2"/>
  {zones("hatch")}
  <rect class="headlight-t" x="58" y="60" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="158" y="60" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="78" y="422" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="138" y="422" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="54" y="72" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="173" y="72" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="34" y="156" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="188" y="156" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="40" y="110" width="11" height="40" rx="3" fill="#111"/>
  <rect x="189" y="110" width="11" height="40" rx="3" fill="#111"/>
  <rect x="44" y="320" width="11" height="40" rx="3" fill="#111"/>
  <rect x="185" y="320" width="11" height="40" rx="3" fill="#111"/>
  <path d="M70,210 L170,210" fill="none" stroke="#000" stroke-opacity="0.25" stroke-width="0.8"/>
'''

SUV_TOP = (
    "M70,48 C58,56 50,80 48,114 "
    "L44,180 L42,260 L46,350 L54,410 "
    "C60,438 84,456 120,460 "
    "C156,456 180,438 186,410 "
    "L194,350 L198,260 L196,180 "
    "L192,114 C190,80 182,56 170,48 "
    "C156,34 84,34 70,48 Z"
)
SUV_TOP_EX = f'''
  <path d="M66,155 L174,155 L166,265 L74,265 Z" fill="url(#suv-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M74,267 L166,267 L156,395 L84,395 Z" fill="url(#suv-glassTop)" opacity="0.8" stroke="#2a3844" stroke-width="0.7"/>
  <!-- racks -->
  <path d="M86,170 L86,250 M154,170 L154,250" stroke="#2a2a30" stroke-width="3"/>
  <path d="M98,58 L120,78 L142,58" fill="none" stroke="#111" stroke-width="2"/>
  {zones("suv")}
  <rect class="headlight-t" x="52" y="58" width="26" height="12" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="162" y="58" width="26" height="12" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="70" y="426" width="28" height="12" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="142" y="426" width="28" height="12" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="50" y="72" width="14" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="176" y="72" width="14" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="26" y="152" width="20" height="10" rx="2" fill="#16161a"/>
  <rect x="194" y="152" width="20" height="10" rx="2" fill="#16161a"/>
  <rect x="34" y="108" width="12" height="44" rx="3" fill="#111"/>
  <rect x="194" y="108" width="12" height="44" rx="3" fill="#111"/>
  <rect x="36" y="318" width="12" height="44" rx="3" fill="#111"/>
  <rect x="192" y="318" width="12" height="44" rx="3" fill="#111"/>
  <path d="M66,210 L174,210" fill="none" stroke="#000" stroke-opacity="0.25" stroke-width="0.8"/>
'''

PICKUP_TOP = (
    "M76,50 C64,58 56,82 54,114 "
    "L50,175 L50,250 L54,300 "
    "L58,310 L58,430 "          # caçamba mais estreita nas laterais internas? na verdade a caçamba é quase a mesma largura
    "C62,448 86,458 120,460 "
    "C154,458 178,448 182,430 "
    "L186,310 L190,250 L190,175 "
    "L186,114 C184,82 176,58 164,50 "
    "C150,36 90,36 76,50 Z"
)
PICKUP_TOP_EX = f'''
  <path d="M68,155 L172,155 L164,250 L76,250 Z" fill="url(#pickup-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M76,252 L164,252 L160,300 L80,300 Z" fill="#1a1010" opacity="0.5"/>
  <!-- caçamba -->
  <path d="M62,312 L178,312 L178,438 L62,438 Z" fill="none" stroke="#111" stroke-width="2"/>
  <path d="M70,320 L170,320 L170,430 L70,430 Z" fill="#1a1a1e" opacity="0.35" stroke="#2a2a30" stroke-width="1"/>
  <path d="M62,438 L178,438" stroke="#111" stroke-width="3"/>
  <path d="M100,58 L120,76 L140,58" fill="none" stroke="#111" stroke-width="2"/>
  {zones("pickup")}
  <rect class="headlight-t" x="54" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="162" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="64" y="440" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="152" y="440" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="50" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="177" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="30" y="152" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="192" y="152" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="38" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="191" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="40" y="340" width="11" height="40" rx="3" fill="#111"/>
  <rect x="189" y="340" width="11" height="40" rx="3" fill="#111"/>
'''

COUPE_TOP = (
    "M82,56 C68,64 58,86 56,118 "
    "L52,180 L52,250 L58,330 L70,400 "
    "C78,430 96,448 120,452 "
    "C144,448 162,430 170,400 "
    "L182,330 L188,250 L188,180 "
    "L184,118 C182,86 172,64 158,56 "
    "C146,40 94,40 82,56 Z"
)
COUPE_TOP_EX = f'''
  <path d="M72,165 L168,165 L158,280 L82,280 Z" fill="url(#coupe-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M84,282 L156,282 L146,370 L94,370 Z" fill="url(#coupe-glassTop)" opacity="0.8" stroke="#2a3844" stroke-width="0.7"/>
  <path d="M100,60 L120,78 L140,60" fill="none" stroke="#111" stroke-width="2"/>
  {zones("coupe")}
  <rect class="headlight-t" x="56" y="62" width="26" height="11" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="158" y="62" width="26" height="11" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="78" y="418" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="138" y="418" width="24" height="11" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="52" y="74" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="175" y="74" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="32" y="162" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="190" y="162" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="40" y="112" width="11" height="40" rx="3" fill="#111"/>
  <rect x="189" y="112" width="11" height="40" rx="3" fill="#111"/>
  <rect x="48" y="318" width="11" height="40" rx="3" fill="#111"/>
  <rect x="181" y="318" width="11" height="40" rx="3" fill="#111"/>
  <!-- uma só quebra de porta -->
  <path d="M72,210 L168,210" fill="none" stroke="#000" stroke-opacity="0.25" stroke-width="0.8"/>
'''

WAGON_TOP = (
    "M78,52 C66,58 56,80 54,110 "
    "L50,170 L48,250 L50,340 L56,410 "
    "C62,436 84,452 120,456 "
    "C156,452 178,436 184,410 "
    "L190,340 L192,250 L190,170 "
    "L186,110 C184,80 174,58 162,52 "
    "C148,38 92,38 78,52 Z"
)
WAGON_TOP_EX = f'''
  <path d="M68,158 L172,158 L164,250 L76,250 Z" fill="url(#wagon-glassTop)" stroke="#2a3844" stroke-width="0.8"/>
  <path d="M76,252 L164,252 L156,410 L84,410 Z" fill="url(#wagon-glassTop)" opacity="0.8" stroke="#2a3844" stroke-width="0.7"/>
  <!-- racks -->
  <path d="M88,180 L88,300 M152,180 L152,300" stroke="#2a2a30" stroke-width="2.6"/>
  <path d="M98,56 L120,74 L142,56" fill="none" stroke="#111" stroke-width="2"/>
  {zones("wagon")}
  <rect class="headlight-t" x="56" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="headlight-t" x="160" y="58" width="24" height="11" rx="2" fill="#c8cce0"/>
  <rect class="taillight-t" x="72" y="424" width="26" height="11" rx="2" fill="#4a0000"/>
  <rect class="taillight-t" x="142" y="424" width="26" height="11" rx="2" fill="#4a0000"/>
  <rect class="turn-tl" x="52" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect class="turn-tr" x="175" y="70" width="13" height="8" rx="1" fill="#ffb000" opacity="0"/>
  <rect x="32" y="154" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="190" y="154" width="18" height="9" rx="2" fill="#16161a"/>
  <rect x="38" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="191" y="108" width="11" height="40" rx="3" fill="#111"/>
  <rect x="40" y="330" width="11" height="40" rx="3" fill="#111"/>
  <rect x="189" y="330" width="11" height="40" rx="3" fill="#111"/>
  <path d="M68,200 L172,200 M68,250 L172,250 M68,330 L172,330" fill="none" stroke="#000" stroke-opacity="0.22" stroke-width="0.8"/>
'''



CARS = {
    "sedan":  ("Sedã", SEDAN_BODY, SEDAN_EXTRAS, 200, 800, 248, 68, SEDAN_TOP, SEDAN_TOP_EX),
    "hatch":  ("Hatch", HATCH_BODY, HATCH_EXTRAS, 200, 792, 248, 68, HATCH_TOP, HATCH_TOP_EX),
    "suv":    ("SUV", SUV_BODY, SUV_EXTRAS, 205, 800, 252, 70, SUV_TOP, SUV_TOP_EX),
    "pickup": ("Picape", PICKUP_BODY, PICKUP_EXTRAS, 200, 805, 252, 70, PICKUP_TOP, PICKUP_TOP_EX),
    "coupe":  ("Cupê", COUPE_BODY, COUPE_EXTRAS, 210, 800, 248, 70, COUPE_TOP, COUPE_TOP_EX),
    "wagon":  ("Perua / wagon", WAGON_BODY, WAGON_EXTRAS, 200, 800, 248, 68, WAGON_TOP, WAGON_TOP_EX),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (label, body, extras, fx, rx, cy, r, top, top_ex) in CARS.items():
        side = side_svg(key, label, body, extras, fx, rx, cy, r)
        (OUT / f"{key}.svg").write_text(side, encoding="utf-8")
        (OUT / f"{key}-top.svg").write_text(top_svg(key, label, top, top_ex), encoding="utf-8")
        print("wrote", key)
    print("OK", OUT)


if __name__ == "__main__":
    main()
