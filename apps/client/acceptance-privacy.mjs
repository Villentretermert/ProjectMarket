import {chromium} from 'playwright';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';
import {privacyAcceptance} from './privacy-acceptance.mjs';
let input='';for await(const part of process.stdin)input+=part;const config=JSON.parse(input),checks=[];
const browser=await chromium.launch({channel:process.env.MARKETOB_BROWSER_CHANNEL||undefined,headless:true});
try{
  await privacyAcceptance(browser,config,async(name,fn)=>{await fn();checks.push(name);console.log('PASS: '+name);});
  await writeFile(path.join(config.output,'browser-results.json'),JSON.stringify({checks,browser:browser.version(),viewport:[1440,1000,360,800],live_metrics:config.liveMetrics},null,2)+'\n');
}finally{await browser.close();}
