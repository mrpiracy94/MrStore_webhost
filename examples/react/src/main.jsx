import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
function App() {
  const [count, setCount] = useState(0);
  return <div style={{background:'#111827', color:'#e5e7eb',minHeight:'100vh',display:'grid',placeItems:'center',fontFamily:'system-ui'}}>
    <div style={{textAlign:'center'}}><h1 style={{color:'#6ee7b7'}}>⚛️ React no ZimaOS</h1>
      <p>Um projeto React compilado automaticamente pelo WebHost.</p>
      <button style={{fontSize:20,padding:14,borderRadius:10}} onClick={()=>setCount(count+1)}>Cliques: {count}</button>
    </div></div>;
}
createRoot(document.getElementById('root')).render(<App />);