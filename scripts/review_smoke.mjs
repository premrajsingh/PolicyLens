import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const base = process.env.APP_URL || 'http://127.0.0.1:8000';
const out = process.env.SMOKE_OUTPUT || 'outputs/e2e-review';
mkdirSync(out,{recursive:true});
const browser = await chromium.launch({headless:true, ...(process.env.PLAYWRIGHT_CHROMIUM_PATH ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_PATH} : {})});
const page = await browser.newPage({viewport:{width:1440,height:1050}});
const errors=[]; page.on('pageerror',e=>errors.push(e.message));
const results=[];
async function check(name,fn) {await fn();results.push(name);console.log('PASS',name);}
try {
 await page.goto(base,{waitUntil:'networkidle'});
 await check('Dashboard uses live portfolio data',async()=>{await page.getByRole('heading',{name:'Policy overview'}).waitFor();assert.ok(await page.getByText('Policy library',{exact:true}).isVisible());});
 await page.screenshot({path:out+'/dashboard-desktop.png',fullPage:true});
 const docs=await (await fetch(base+'/api/documents')).json();
 const selected=docs.documents.find(d=>/1.Policy/.test(d.filename)) || docs.documents[0];
 if(selected) {
  await page.goto(`${base}/workspace?doc=${selected.id}`,{waitUntil:'networkidle'});
  await check('Extraction sections are accessible',async()=>{assert.equal(await page.getByRole('tab').count(),12);await page.getByRole('tab',{name:/Maternity/}).click();});
  await check('Maternity fields expose evidence and conditions',async()=>{await page.locator('details').filter({hasText:'Normal delivery'}).first().locator('summary').click();assert.ok(await page.getByText(/Source · page/).first().isVisible());});
  await page.screenshot({path:out+'/extraction-desktop.png',fullPage:true});
  await check('Download URL and PDF source work',async()=>{for(const path of [`/api/policies/${selected.id}/download`,`/api/documents/${selected.id}/file`]) assert.equal((await fetch(base+path)).status,200);});
  await check('Every section renders without a crash',async()=>{for(const tab of await page.getByRole('tab').all()) await tab.click();});
 }
 for (const route of ['/knowledge-base','/evidence','/compare','/settings']) {
  await page.goto(base+route,{waitUntil:'networkidle'}); await page.locator('h1').waitFor();
  await check('Route '+route,async()=>assert.equal(await page.locator('h1').count(),1));
 }
 await page.setViewportSize({width:390,height:844});
 for(const route of ['/', '/knowledge-base', ...(selected?[`/workspace?doc=${selected.id}`]:[]),'/compare']) {
  await page.goto(base+route,{waitUntil:'networkidle'});
  await check('Mobile fits '+route,async()=>{assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));});
 }
 await page.screenshot({path:out+'/extraction-mobile.png',fullPage:true});
 await page.goto(base,{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Open navigation'}).click();
 await page.getByRole('link',{name:'Policies',exact:true}).last().click();
 await check('Mobile navigation closes after selection',async()=>assert.equal(await page.getByRole('button',{name:'Close navigation'}).count(),0));
 await page.setViewportSize({width:1440,height:1050});await page.goto(base,{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Dark mode',exact:true}).click();
 await page.screenshot({path:out+'/dashboard-dark.png',fullPage:true});
 await check('No browser exceptions',async()=>assert.deepEqual(errors,[]));
} finally {
 writeFileSync(out+'/results.json',JSON.stringify({passed:results.length,results,errors},null,2));
 await browser.close();
}
