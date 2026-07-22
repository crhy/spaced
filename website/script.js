const header=document.querySelector('.header');
const menu=document.querySelector('.menu');
const nav=document.querySelector('nav');
const copyStatus=document.querySelector('.copy-status');
const lightbox=document.querySelector('#lightbox');
const lightboxImage=lightbox?.querySelector('img');
const lightboxCaption=lightbox?.querySelector('p');
const lightboxClose=lightbox?.querySelector('.lightbox-close');

addEventListener('scroll',()=>header.classList.toggle('scrolled',scrollY>20));
menu.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open))});
nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}));

document.querySelectorAll('.copy-button').forEach(button=>{
  button.addEventListener('click',async()=>{
    const text=button.dataset.copy||'';
    try{await navigator.clipboard.writeText(text);copyStatus.textContent='Copied to clipboard.'}
    catch{copyStatus.textContent=`Copy this value: ${text}`}
    setTimeout(()=>{copyStatus.textContent=''},3500);
  });
});

document.querySelectorAll('.screenshot-button').forEach(button=>{
  button.addEventListener('click',()=>{
    if(!lightbox||!lightboxImage)return;
    lightboxImage.src=button.dataset.image||button.querySelector('img')?.src||'';
    lightboxImage.alt=button.querySelector('img')?.alt||'';
    lightboxCaption.textContent=button.dataset.title||'';
    lightbox.showModal();
  });
});

lightboxClose?.addEventListener('click',()=>lightbox.close());
lightbox?.addEventListener('click',event=>{if(event.target===lightbox)lightbox.close()});
addEventListener('keydown',event=>{if(event.key==='Escape'&&lightbox?.open)lightbox.close()});
