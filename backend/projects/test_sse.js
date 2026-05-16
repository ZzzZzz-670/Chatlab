// SSE stream test script - simulates frontend streaming decode
async function testSSE() {
  const response = await fetch('http://localhost:5000/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'default',
      session_id: 'test-sse-' + Date.now(),
      messages: [{ role: 'user', content: '孩子最近总玩手机，作业写到很晚，怎么办' }],
      stream: true
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: false });
  let buffer = '';
  let fullContent = '';
  let chunkCount = 0;
  let hasGarbled = false;

  function processLines(raw) {
    const lines = raw.split(/\r?\n/);
    for (const line of lines) {
      if (!line.trim() || !line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (data === '[DONE]') continue;
      try {
        const parsed = JSON.parse(data);
        const delta = parsed.choices?.[0]?.delta;
        if (delta?.content) {
          fullContent += delta.content;
          chunkCount++;
          // Check for replacement character
          if (delta.content.includes('\uFFFD')) {
            hasGarbled = true;
            console.log('GARBLED chunk:', JSON.stringify(delta.content));
          }
        }
      } catch (e) {
        // console.log('Parse error:', e.message, 'data:', data.slice(0, 50));
      }
    }
  }

  const startTime = Date.now();
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      const tail = decoder.decode();
      if (tail) buffer += tail;
      if (buffer.trim()) processLines(buffer);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';
    if (lines.length) processLines(lines.join('\n'));
  }
  const elapsed = Date.now() - startTime;

  console.log('\n=== SSE Test Result ===');
  console.log('Total chunks:', chunkCount);
  console.log('Elapsed ms:', elapsed);
  console.log('Has garbled:', hasGarbled);
  console.log('Full content length:', fullContent.length);
  console.log('Full content (first 200 chars):', fullContent.slice(0, 200));
  console.log('Full content (last 200 chars):', fullContent.slice(-200));

  // Check for replacement characters in final content
  const replacements = (fullContent.match(/\uFFFD/g) || []).length;
  console.log('Replacement chars in final:', replacements);

  if (hasGarbled || replacements > 0) {
    console.log('\n!!! GARBLED TEXT FOUND !!!');
    // Find context around garbled chars
    for (let i = 0; i < fullContent.length; i++) {
      if (fullContent[i] === '\uFFFD') {
        const start = Math.max(0, i - 20);
        const end = Math.min(fullContent.length, i + 21);
        console.log('Context:', JSON.stringify(fullContent.slice(start, end)));
      }
    }
  }
}

testSSE().catch(console.error);
