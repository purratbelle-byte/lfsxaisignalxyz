const markets=["USD/MXN OTC","USD/PKR OTC","EUR/CHF OTC"];
let selected=markets[0];
const box=document.getElementById("markets");
markets.forEach((m,i)=>{const b=document.createElement("button");b.className="market"+(i===0?" active":"");b.textContent=m;b.onclick=()=>{selected=m;document.querySelectorAll(".market").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.getElementById("symbol").textContent=m;};box.appendChild(b);});
function render(d){
 document.getElementById("signal").textContent=d.direction||d.status||"WAITING";
 document.getElementById("up").textContent=(d.up_probability??0)+"%";
 document.getElementById("down").textContent=(d.down_probability??0)+"%";
 document.getElementById("pattern").textContent=d.pattern_id||"—";
 document.getElementById("matches").textContent=d.matches??0;
}
render({status:"WAITING",direction:"WAITING"});
