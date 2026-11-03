export const editorialCss = `
:root{--ink:#111;--ink-2:#242424;--accent:#111;--paper:#fff;--paper-bright:#fff;--soft:#f6f6f4;--sand:#ecece8;--line:#d6d6d2;--muted:#4b4b49;--rust:#a12b1f;--signal-red:#a12b1f;--mint:#dce9df;--navy:#111;--heading-sm:1.25rem;--heading-md:clamp(1.9rem,3.2vw,2.8rem);--heading-lg:clamp(2.8rem,5vw,4.15rem)}
body{background:#fff;color:var(--ink)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline-color:#111}
.site-header{top:0;background:rgba(255,255,255,.98);border-color:#111}
.header-inner{min-height:74px;gap:28px}
.brand-mark{filter:grayscale(1) contrast(1.7);width:38px;height:38px}
.wordmark{gap:10px;color:#111;letter-spacing:.08em}
.primary-nav{gap:0}
.primary-nav a{min-height:74px;padding:0 17px;color:#111;font-size:.78rem;letter-spacing:.035em;text-transform:none;border:0;border-bottom:3px solid transparent}
.primary-nav a:hover,.primary-nav a:focus-visible,.primary-nav a[aria-current]{color:#111;background:var(--soft);border-bottom-color:#111}
h1,.hero h1,.page-intro h1,.data-intro h1,.dossier-header h1,.not-found h1{font-size:var(--heading-lg);line-height:1.02;letter-spacing:-.035em}
h2,.preview-heading h2,.signal-catalog h2,.candidate-warning h2,.dossier-grid h2,.dossier-sources h2{font-size:var(--heading-md);line-height:1.1;letter-spacing:-.025em}
.kicker,.eyebrow,.section-number{color:#111;letter-spacing:.055em}
.primary{background:#111;color:#fff}.primary:hover{background:#333}
.secondary{border-color:#111;background:#fff;color:#111}.secondary:hover{background:#111;color:#fff}
.editorial-hero{width:auto;min-height:0;margin:0;padding:76px 0 68px;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.72fr);gap:84px;align-items:end;overflow:visible;border-bottom:1px solid #111}
.editorial-hero .hero-copy{position:static;width:auto;margin:0;padding:0;background:#fff;border:0}
.editorial-hero .eyebrow{margin:0 0 25px;font-size:.82rem;font-weight:800;text-transform:uppercase}
.editorial-hero h1{max-width:760px;margin:0 0 24px}
.editorial-hero .lede{max-width:680px;margin:0;color:var(--muted);font-size:1.16rem}
.home-search{margin-top:36px}
.home-search label{display:block;margin-bottom:8px;font-size:.8rem;font-weight:800}
.home-search>div{display:grid;grid-template-columns:minmax(0,1fr) auto;max-width:680px}
.home-search input{min-height:52px;padding:12px 14px;border:1px solid #111;border-right:0;background:#fff;color:#111;font-size:1rem}
.home-search button{min-height:52px;padding:0 22px;border:1px solid #111;background:#111;color:#fff;font-weight:800;cursor:pointer}
.home-search button:hover{background:#333}
.home-ledger{border-top:6px solid #111;background:#111;color:#fff}
.home-ledger header{display:flex;justify-content:space-between;gap:18px;padding:18px 22px;border-bottom:1px solid #555;font-size:.75rem}
.home-ledger header span{font-weight:800;text-transform:uppercase;letter-spacing:.06em}
.home-ledger time{color:#cfcfcb}
.home-ledger dl{margin:0}
.home-ledger dl div{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:baseline;padding:17px 22px;border-bottom:1px solid #444}
.home-ledger dt{color:#d4d4d0;font-size:.85rem}
.home-ledger dd{margin:0;font-size:1.35rem;font-weight:800;font-variant-numeric:tabular-nums}
.home-ledger>a{display:flex;justify-content:space-between;gap:18px;padding:20px 22px;color:#fff;font-weight:800;text-decoration:none}
.home-ledger>a:hover{background:#2b2b2b}
.budget-stage-line{padding:52px 0 62px;border-bottom:1px solid var(--line)}
.budget-stage-line header{display:flex;justify-content:space-between;gap:32px;align-items:end;margin-bottom:28px}
.budget-stage-line header p{margin:0}.budget-stage-line h2{font-size:1.65rem}
.budget-stage-line ol{display:grid;grid-template-columns:repeat(5,1fr);margin:0;padding:0;list-style:none;border-top:1px solid #111;border-bottom:1px solid #111}
.budget-stage-line li{min-height:132px;padding:20px 16px;background:#fff}
.budget-stage-line li+li{border-left:1px solid var(--line)}
.budget-stage-line li span,.budget-stage-line li strong,.budget-stage-line li small{display:block}
.budget-stage-line li span{font-size:.75rem;font-weight:800}
.budget-stage-line li strong{margin-top:20px;font-size:.95rem}
.budget-stage-line li small{margin-top:5px;color:var(--muted)}
.budget-stage-line li.complete{box-shadow:inset 0 5px 0 #2f684f}.budget-stage-line li.partial{box-shadow:inset 0 5px 0 #a12b1f}
.budget-stage-line>a{display:inline-flex;margin-top:20px;gap:18px;font-weight:800;color:#111}
.register-preview{padding:72px 0 82px}
.preview-heading{grid-template-columns:220px minmax(0,1fr);gap:34px;margin-bottom:32px}
.preview-heading .kicker{color:#111}
.preview-panels{grid-template-columns:repeat(4,1fr);border-color:#111}
.preview-panels>a{min-height:245px;padding:24px;color:#111}
.preview-panels>a>span,.preview-panels article>span{display:block;width:auto;height:auto;border-radius:0;background:transparent;color:#111;font-size:.8rem;text-align:left}
.preview-panels>a div,.preview-panels article div{margin:32px 0 auto}
.preview-panels h3{margin:0 0 10px;font-size:1.2rem}
.preview-panels small{color:#111;letter-spacing:.04em}
.preview-panels small:before{border-radius:0;background:#111}
.preview-panels>a:hover{background:var(--soft)}
.home-questions{display:grid;grid-template-columns:minmax(240px,.65fr) minmax(0,1.35fr);gap:70px;padding:76px 0 90px;border-top:1px solid #111}
.home-questions header .kicker{margin:0 0 15px}.home-questions header h2{max-width:420px}
.home-questions>div{border-top:1px solid #111}
.home-questions a{display:grid;grid-template-columns:110px minmax(0,1fr) auto;gap:22px;align-items:center;padding:24px 0;border-bottom:1px solid var(--line);color:#111;text-decoration:none}
.home-questions a:hover{background:var(--soft)}
.home-questions a span{font-size:.78rem;font-weight:800;text-transform:uppercase}.home-questions a strong{font-size:1.12rem}.home-questions a b{font-size:1.3rem}
.home-boundary{display:grid;grid-template-columns:200px minmax(0,1fr) auto;gap:30px;align-items:start;padding:28px 0 68px;border-top:1px solid #111}
.home-boundary strong{font-size:1.05rem}.home-boundary p{max-width:690px;margin:0;color:var(--muted)}.home-boundary a{color:#111;font-weight:800;white-space:nowrap}
.data-intro,.page-intro{padding-top:72px;gap:56px}
.data-intro h1,.page-intro h1{margin-top:15px}
.snapshot-card,.value-verdict{border:0;border-top:5px solid #111;background:#111;color:#fff}
.snapshot-card span,.snapshot-card p,.value-verdict span,.value-verdict p{color:#d6d6d2}
.snapshot-card a{color:#fff}
.value-hero{background:#111}.value-hero .kicker{color:#fff}.value-hero .lede{color:#dededa}
.value-boundary,.agency-disclaimer,.change-disclaimer,.review-warning,.integrity-warning,.cycle-boundary{border-color:#111;background:#fff}
.value-boundary strong,.agency-disclaimer strong,.cycle-boundary strong{color:#111}
.value-summary,.agency-summary,.change-summary,.review-summary,.integrity-summary,.dataset-stats{border-color:#111}
.value-indicator .direction,.agency-badge,.change-badge,.review-badge,.integrity-badge,.record-type{border-radius:0;background:#333;color:#fff}
.value-indicator .direction.improving,.cycle-status.verified,.agency-badge.verified{background:#dce9df;color:#173c2b}
.value-indicator .direction.pressure,.agency-badge.increase,.change-badge.house_only,.review-badge{background:#f3dfdb;color:#772018}
.value-filters button,.explorer-controls button,.agency-controls button,.change-controls button,.review-controls button,.integrity-controls button{min-height:44px;border-color:#111}
.explorer-controls button,.explorer-actions button,.agency-controls button,.agency-actions button,.change-controls button,.change-actions button,.review-controls button,.integrity-controls button,.contractor-controls button,.concentration-controls button{background:#111;color:#fff;border-color:#111}
.explorer-controls .secondary-control,.agency-controls button.secondary-control,.change-controls button.secondary-control{background:#fff;color:#111}
.value-filters button[aria-pressed="true"],.explorer-tabs button[aria-selected="true"]{background:#111;color:#fff}
.explorer-shell,.agency-shell,.change-shell,.review-shell,.integrity-shell,.contractor-shell{border-color:#111;box-shadow:none}
.record-card:hover,.agency-card:hover,.change-card:hover,.review-record:hover,.integrity-record:hover{background:var(--soft)}
.record-links a,.agency-evidence a,.change-evidence a,.review-record-links a,.review-toolbar a,.integrity-links a,.integrity-toolbar a,.integrity-record-links a,.contractor-record a,.cycle-document a,.opportunity-panel a,.value-indicator a,.signal-catalog a,.district-context li a{color:#111;text-decoration-thickness:1px;text-underline-offset:3px}
.value-comparison b{color:#111}
.dataset-stats span,.value-test span,.pipeline-group>span,.pipeline-group li:before,.policy-item span,.contractor-record:before{color:#111}
.integrity-badge{background:#111;color:#fff}.integrity-badge.classification{border:1px solid #111;background:#fff;color:#111}
.agency-badge{background:#111;color:#fff}.agency-badge.increase{background:#f3dfdb;color:#772018}.agency-badge.decrease{background:#e9e9e6;color:#111}.agency-badge.unavailable{background:#e9e9e6;color:#4b4b49}
.change-badge{background:#111;color:#fff}.change-badge.house_only{background:#f3dfdb;color:#772018}.change-badge.nep_only{background:#e9e9e6;color:#111}.change-badge.quarantine{background:#f3ead5;color:#6b4700}
.review-badge{background:#f3dfdb;color:#772018}.review-badge.dataset{background:#111;color:#fff}.review-badge.quarantine{background:#f3ead5;color:#6b4700}
.agency-method,.change-scope,.review-method,.cycle-note,.value-sources,.candidate-warning,.signal-band{background:#111;color:#fff}
.agency-method p,.change-scope p,.review-method p,.cycle-note p,.value-sources p,.candidate-warning p,.signal-layout>div>p:last-child{color:#d6d6d2}
.cycle-stage.available b,.cycle-stage.partial b{background:#e5eee8;color:#173c2b}.cycle-stage.unavailable{background:#f4f4f1}
.cycle-map,.cycle-document-list{border-color:#111}
.local-nav{padding:10px 0;border-width:1px 0;background:#fff}
.local-nav a{min-height:44px}.local-nav a:hover{background:#111;color:#fff}
.policy-grid,.standards-grid{gap:0}.policy-item,.standard-panel{border-color:var(--line)}
.site-footer{background:#fff;border-color:#111}.footer-nav{flex-wrap:wrap}.footer-nav a{text-transform:none;letter-spacing:0;color:#111}
@media(max-width:980px){
  .editorial-hero{grid-template-columns:1fr;gap:44px;padding:62px 0}.editorial-hero .hero-copy{order:0}.home-ledger{order:1;max-width:680px}
  .preview-panels{grid-template-columns:1fr 1fr}.preview-panels>a:nth-child(3){border-left:0;border-top:1px solid var(--line)}.preview-panels>a:nth-child(4){border-top:1px solid var(--line)}
  .budget-stage-line ol{grid-template-columns:1fr 1fr}.budget-stage-line li:nth-child(odd){border-left:0}.budget-stage-line li:nth-child(n+3){border-top:1px solid var(--line)}
  .home-questions{grid-template-columns:1fr;gap:34px}
}
@media(max-width:720px){
  html{scroll-padding-top:126px}.header-inner{min-height:0;padding:9px 0 0;gap:8px}.wordmark{min-height:45px}.brand-mark{width:34px;height:34px}
  .primary-nav{display:grid;grid-template-columns:repeat(5,1fr);width:100%;border-top:1px solid var(--line)}
  .primary-nav a{min-height:48px;padding:0 2px;font-size:.7rem;letter-spacing:0;text-align:center;justify-content:center}
  .editorial-hero{padding:48px 0 50px}.editorial-hero h1{font-size:clamp(2.55rem,12vw,3.2rem)}.editorial-hero .lede{font-size:1rem}
  .home-search>div{grid-template-columns:1fr}.home-search input{border-right:1px solid #111;border-bottom:0}.home-search button{width:100%}
  .home-ledger header{display:grid}.home-ledger dl div{grid-template-columns:1fr}.home-ledger dd{font-size:1.25rem}
  .budget-stage-line header{display:grid;gap:8px}.budget-stage-line ol{grid-template-columns:1fr}.budget-stage-line li+li{border-left:0;border-top:1px solid var(--line)}
  .preview-heading{grid-template-columns:1fr}.preview-panels{grid-template-columns:1fr}.preview-panels>a{min-height:210px}.preview-panels>a+a,.preview-panels>a:nth-child(3){border-left:0;border-top:1px solid var(--line)}
  .home-questions a{grid-template-columns:1fr auto}.home-questions a span{grid-column:1/-1}.home-questions a b{grid-column:2;grid-row:2}
  .home-boundary{grid-template-columns:1fr;gap:12px}.home-boundary a{white-space:normal}
  .data-intro,.page-intro{padding-top:54px}.footer-inner{gap:24px}
}
@media(prefers-contrast:more){:root{--line:#70706c;--muted:#252523}}
`;
