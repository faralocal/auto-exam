const t={success:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>',error:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',warning:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',info:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'},n={
/**
   * Adds a generic toast notification.
   * @param {string} message - The message to display.
   * @param {'success'|'error'|'warning'|'info'} [type='info'] - The type of toast.
   * @param {number} [duration=3000] - Duration in ms.
   */
add:(t,n,o)=>{},
/**
   * Shows a success notification (Green).
   * @param {string} message - The message to display.
   * @param {number} [duration=3000] - Duration in ms.
   */
success:(t,o)=>n.add(t,"success",o),
/**
   * Shows an error notification (Red).
   * @param {string} message - The message to display.
   * @param {number} [duration=3000] - Duration in ms.
   */
error:(t,o)=>n.add(t,"error",o),
/**
   * Shows a warning notification (Yellow).
   * @param {string} message - The message to display.
   * @param {number} [duration=3000] - Duration in ms.
   */
warning:(t,o)=>n.add(t,"warning",o),
/**
   * Shows an info notification (Blue).
   * @param {string} message - The message to display.
   * @param {number} [duration=3000] - Duration in ms.
   */
info:(t,o)=>n.add(t,"info",o)},o={
/**
   * Installs the plugin into the Zog application.
   * @param {Object} api - The Zog instance API (contains reactive, ref, etc.).
   * @param {ToastOptions} [options={}] - Configuration options.
   */
install(o,e={}){const{reactive:s}=o,i=e.defaultDuration||3e3,r=e.position||"bottom-right";(()=>{if(document.getElementById("z-toast-styles"))return;const t=document.createElement("style");t.id="z-toast-styles",t.textContent='\n/* Base Container */\n.z-toast-container {\n    position: fixed;\n    display: flex;\n    flex-direction: column;\n    gap: 10px;\n    z-index: 9999;\n    pointer-events: none;\n    transition: all 0.3s ease;\n}\n\n/* Positioning Classes */\n.z-pos-top-right { top: 20px; right: 20px; align-items: flex-end; }\n.z-pos-bottom-right { bottom: 20px; right: 20px; align-items: flex-end; }\n.z-pos-top-left { top: 20px; left: 20px; align-items: flex-start; }\n.z-pos-bottom-left { bottom: 20px; left: 20px; align-items: flex-start; }\n\n/* Center Positioning */\n.z-pos-top-center { top: 20px; left: 50%; transform: translateX(-50%); align-items: center; }\n.z-pos-bottom-center { bottom: 20px; left: 50%; transform: translateX(-50%); align-items: center; }\n\n/* Toast Item */\n.z-toast {\n    display: flex;\n    align-items: center;\n    min-width: 300px;\n    max-width: 450px;\n    padding: 12px 16px;\n    background: #ffffff;\n    border-radius: 8px;\n    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);\n    border-left: 4px solid transparent;\n    pointer-events: auto;\n    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;\n    font-size: 14px;\n    color: #333;\n    cursor: pointer;\n    opacity: 0;\n    transition: opacity 0.3s ease, transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);\n}\n\n/* Icons & Colors */\n.z-toast-icon { width: 20px; height: 20px; margin-right: 12px; flex-shrink: 0; }\n.z-toast-success { border-left-color: #10b981; } .z-toast-success .z-toast-icon { color: #10b981; }\n.z-toast-error { border-left-color: #ef4444; } .z-toast-error .z-toast-icon { color: #ef4444; }\n.z-toast-warning { border-left-color: #f59e0b; } .z-toast-warning .z-toast-icon { color: #f59e0b; }\n.z-toast-info { border-left-color: #3b82f6; } .z-toast-info .z-toast-icon { color: #3b82f6; }\n\n/* Dynamic Entry Animations */\n.z-pos-top-right .z-toast, .z-pos-bottom-right .z-toast { transform: translateX(30px); }\n.z-pos-top-left .z-toast, .z-pos-bottom-left .z-toast { transform: translateX(-30px); }\n.z-pos-top-center .z-toast { transform: translateY(-30px); }\n.z-pos-bottom-center .z-toast { transform: translateY(30px); }\n\n/* Visible State */\n.z-toast.z-toast-visible {\n    opacity: 1;\n    transform: translate(0, 0) !important;\n}\n',document.head.appendChild(t)})();let a=document.querySelector(".z-toast-container");a?a.className=`z-toast-container z-pos-${r}`:(a=document.createElement("div"),a.className=`z-toast-container z-pos-${r}`,document.body.appendChild(a));const l=s({toasts:[]}),c=/* @__PURE__ */new Map,p=t=>{const n=c.get(t);n&&(n.classList.remove("z-toast-visible"),setTimeout(()=>{n.parentNode&&n.parentNode.removeChild(n),c.delete(t)},300));const o=l.toasts.findIndex(n=>n.id===t);o>-1&&l.toasts.splice(o,1)};n.add=(n,o="info",e=i)=>{const s=Date.now()+Math.random().toString(36).substr(2,9);l.toasts.push({id:s,message:n,type:o,duration:e});const d=document.createElement("div");d.className=`z-toast z-toast-${o}`,d.innerHTML=`\n                <div class="z-toast-icon">${t[o]||t.info}</div>\n                <div>${n}</div>\n            `,d.addEventListener("click",()=>p(s)),r.startsWith("top")?a.prepend(d):a.appendChild(d),c.set(s,d),requestAnimationFrame(()=>{requestAnimationFrame(()=>{d.classList.add("z-toast-visible")})}),e>0&&setTimeout(()=>p(s),e)},window.$toast=n}};export{n as $toast,o as ZogToast};
//# sourceMappingURL=zog-toast.es.js.map
