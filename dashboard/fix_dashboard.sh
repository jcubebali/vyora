#!/bin/bash

# Inject Firebase user data ke dashboard.html
cat >> dashboard.html << 'FBEOF'
<script type="module">
import{initializeApp}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import{getAuth,onAuthStateChanged,signOut}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import{getFirestore,doc,getDoc}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";
const app=initializeApp({apiKey:"AIzaSyAmfMQnx-ZkP1e0BkD68d3lvIY5FFv8Rck",authDomain:"nexus-trade-e449e.firebaseapp.com",projectId:"nexus-trade-e449e",storageBucket:"nexus-trade-e449e.firebasestorage.app",messagingSenderId:"354555982240",appId:"1:354555982240:web:4bad26e3507918a5b634c5"});
const auth=getAuth(app);
const db=getFirestore(app);
onAuthStateChanged(auth,async(u)=>{
  if(!u){window.location.href='login.html';return;}
  const snap=await getDoc(doc(db,'users',u.uid));
  if(snap.exists()){
    const d=snap.data();
    // Update nama & plan di sidebar
    const nm=document.getElementById('sidebar-user-name');
    const pl=document.getElementById('sidebar-user-plan');
    if(nm)nm.textContent=d.name||u.email;
    if(pl)pl.textContent='✦ '+(d.plan||'trial').toUpperCase();
    // Update stats
    const pb=document.getElementById('total-profit');
    const bv=document.getElementById('balance-val');
    if(pb)pb.textContent='$'+(d.totalPnl||0).toFixed(4);
    if(bv)bv.textContent='$'+(d.totalUsdt||14.01).toFixed(2);
    // Update plan banner
    if(d.plan==='trial'&&d.trialEndsAt){
      const ends=d.trialEndsAt.toDate?d.trialEndsAt.toDate():new Date(d.trialEndsAt);
      const days=Math.max(0,Math.ceil((ends-new Date())/(864e5)));
      const td=document.getElementById('trial-days');
      if(td)td.textContent=days;
    }
  }
});
window.doLogout=async()=>{
  if(confirm('Yakin mau logout?')){
    await signOut(auth);
    window.location.href='login.html';
  }
};
</script>
FBEOF
echo "✅ dashboard.html updated"

# Fix semua nav logout link
for f in signals.html bot.html trades.html ai-chat.html portfolio.html settings.html; do
cat >> $f << 'FBEOF'
<script type="module">
import{initializeApp}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import{getAuth,onAuthStateChanged,signOut}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import{getFirestore,doc,getDoc}from"https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";
const app=initializeApp({apiKey:"AIzaSyAmfMQnx-ZkP1e0BkD68d3lvIY5FFv8Rck",authDomain:"nexus-trade-e449e.firebaseapp.com",projectId:"nexus-trade-e449e",storageBucket:"nexus-trade-e449e.firebasestorage.app",messagingSenderId:"354555982240",appId:"1:354555982240:web:4bad26e3507918a5b634c5"});
const auth=getAuth(app);
const db=getFirestore(app);
onAuthStateChanged(auth,async(u)=>{
  if(!u){window.location.href='login.html';return;}
  const snap=await getDoc(doc(db,'users',u.uid));
  if(snap.exists()){
    const d=snap.data();
    const nm=document.getElementById('sidebar-user-name');
    const pl=document.getElementById('sidebar-user-plan');
    if(nm)nm.textContent=d.name||u.email;
    if(pl)pl.textContent='✦ '+(d.plan||'trial').toUpperCase();
  }
});
window.doLogout=async()=>{
  if(confirm('Yakin mau logout?')){
    await signOut(auth);
    window.location.href='login.html';
  }
};
</script>
FBEOF
echo "✅ $f updated"
done
