const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/options/static/app.js','utf8');
function line(name){return source.split('\n').find(l=>l.startsWith('function '+name+'(')||l.startsWith('async function '+name+'('));}
async function scenario({privacy='public',failX=false}={}){
 const calls=[],memory={};
 const el=()=>({disabled:false,textContent:'',innerHTML:'',dataset:{},setAttribute(){},removeAttribute(){}});
 const status=el(),feedButton=el(),check=el();
 const card={dataset:{newsUrl:'https://example.com/story',newsTitle:'Test story',newsPeak:'AI/I',newsYoutubePublished:'false',newsXPublished:'false'},querySelector(s){return s==='.news-publish-status'?status:s==='.news-publish-btn'?feedButton:s==='.news-workflow-check'?check:null;}};
 const nodes={'#youtube-publish-btn':el(),'#youtube-publish-status':el(),'#youtube-review-confirm':{checked:true},'#youtube-video-title':{value:'Reviewed title'},'#youtube-video-description':{value:'Reviewed description'},'#youtube-series':{value:'policy_power_news'},'#youtube-privacy':{value:privacy}};
 let fail=failX;
 const context=vm.createContext({console,FormData,Blob,Map,Date,document:{querySelectorAll:()=>[card]},$:s=>nodes[s],safe:s=>s,toast(){},loadNews:async()=>{},readApiError:async()=> 'X unavailable',localStorage:{getItem:k=>memory[k],setItem:(k,v)=>memory[k]=v},fetch:async(url,opts)=>{calls.push({url,opts});let data={};if(url.endsWith('/youtube/publish'))data={video_id:'video1',url:'https://youtube.com/watch?v=video1',privacy_status:privacy};if(url.endsWith('/x/publish')){if(fail){fail=false;return {ok:false,status:400};}data={post_id:'post1',url:'https://x.com/rhtc/status/post1'};}return {ok:true,json:async()=>data};}});
 const modal=source.slice(source.indexOf('const analysisYouTubeUploads='),source.indexOf('\nfunction updateAnalysisSpeechControls',source.indexOf('const analysisYouTubeUploads=')));
 const x=source.slice(source.indexOf('async function publishNewsStoryToX('),source.indexOf('async function publishNewsStory(',source.indexOf('async function publishNewsStoryToX(')));
 vm.runInContext(`let activeNewsStory={url:'https://example.com/story'},analysisPodcastAudioBlob=new Blob(['ID3audio']),youtubeReady=true;const X_PENDING_STORAGE_KEY='test';\n`+['readPendingXPosts','writePendingXPost','clearPendingXPost','updateNewsPublishControl','markXPostSaved','savePendingXPost','restorePendingXPost','updateYouTubePublishButton'].map(line).join('\n')+'\n'+x+'\n'+modal,context);
 await vm.runInContext('publishAnalysisToYouTube()',context);
 assert.equal(calls.filter(c=>c.url.endsWith('/youtube/publish')).length,1);
 assert.equal(calls[0].opts.body.get('story_url'),'https://example.com/story');
 if(privacy==='private'){assert.equal(calls.filter(c=>c.url.endsWith('/x/publish')).length,0);assert.equal(check.textContent,'□');return;}
 if(failX){assert.equal(check.textContent,'□');assert.equal(card.dataset.newsYoutubePublished,'true');await vm.runInContext('publishAnalysisToYouTube()',context);assert.equal(calls.filter(c=>c.url.endsWith('/youtube/publish')).length,1);}
 assert.equal(card.dataset.newsXPublished,'true');assert.equal(check.textContent,'✓');assert.equal(feedButton.textContent,'✓ Published');assert.equal(feedButton.disabled,true);
 const xcall=calls.find(c=>c.url.endsWith('/x/publish'));assert.equal(JSON.parse(xcall.opts.body).url,'https://youtube.com/watch?v=video1');
 await vm.runInContext('publishAnalysisToYouTube()',context);
 assert.equal(calls.filter(c=>c.url.endsWith('/youtube/publish')).length,1);
 assert.equal(calls.filter(c=>c.url.endsWith('/x/publish')).length,failX?2:1);
}
(async()=>{await scenario();await scenario({privacy:'unlisted'});await scenario({privacy:'private'});await scenario({failX:true});console.log('PASS: report upload -> X -> both feed indicators; private handling; X-only retry; no duplicate uploads/posts.');})().catch(e=>{console.error(e);process.exitCode=1;});
