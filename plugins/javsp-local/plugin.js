// Reserved built-in adapter. The host calls its fixed metadata-only bridge.
// Ordinary JavaScript plugins receive no process or filesystem capabilities.
function buildRequest(input) { throw new Error('请通过 JavSP 本地辅助引擎运行'); }
function parseResponse(input) { throw new Error('请通过 JavSP 本地辅助引擎运行'); }
