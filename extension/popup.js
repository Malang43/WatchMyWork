chrome.runtime.sendMessage({ type: 'current' }).then(response => {
  document.querySelector('#status').textContent = response?.ok ? (response.data ? `Recording: ${(response.data.input_columns || [response.data.input_column]).join(', ')} → ${response.data.destination_column}` : 'Connected · Ready for a demonstration') : (response?.error || 'Start the local backend to connect.');
}).catch(() => { document.querySelector('#status').textContent = 'Unable to connect. Reload the extension.'; });
