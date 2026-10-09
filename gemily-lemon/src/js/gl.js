/* WebGL post-process: the 2D scene is uploaded as a texture and run through a fragment shader
   (shockwave ripples, chromatic aberration on shake, bloom, vignette, jackpot rainbow). Falls back to plain 2D. */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  const GL = G.GL = { ok: false };

  const VS = `attribute vec2 p; varying vec2 uv; void main(){ uv = p*0.5+0.5; gl_Position = vec4(p,0.,1.); }`;
  const FS = `
precision mediump float;
varying vec2 uv;
uniform sampler2D tex;
uniform vec2 res;
uniform float time, aberr, sat, rainbow, flash, vig, pix;
uniform vec4 rip[4];

vec3 hue(float h){ return clamp(abs(mod(h*6.+vec3(0.,4.,2.),6.)-3.)-1.,0.,1.); }

void main(){
  vec2 q = uv;
  float asp = res.x/res.y;
  vec2 off = vec2(0.);
  float boost = 0.;
  for(int i=0;i<4;i++){
    vec4 r = rip[i];
    if(r.w > 0.001){
      vec2 d = (q - r.xy); d.x *= asp;
      float dist = length(d);
      float w = exp(-pow((dist - r.z)*14., 2.));
      vec2 dir = d/(dist+1e-4);
      vec2 o = dir * w * r.w * 0.016;
      o.x /= asp;
      off += o;
      boost += w * r.w * 0.12;
    }
  }
  q += off;
  vec2 c = (uv - .5);
  float ab = aberr + length(off)*0.5;
  vec2 dir = normalize(c + 1e-4) * ab * (0.4 + length(c));
  vec3 col;
  col.r = texture2D(tex, q + dir).r;
  col.g = texture2D(tex, q).g;
  col.b = texture2D(tex, q - dir).b;
  // cheap bloom: 8 taps, keep only the bright part
  vec3 bl = vec3(0.);
  vec2 px = 1.0/res;
  for(int i=0;i<8;i++){
    float a = float(i)*0.785398;
    vec2 o = vec2(cos(a), sin(a)) * px * 5.0;
    vec3 s = texture2D(tex, q + o).rgb;
    bl += max(s - 0.62, 0.);
    s = texture2D(tex, q + o*2.2).rgb;
    bl += max(s - 0.66, 0.) * 0.7;
  }
  col += bl * 0.16 + boost * vec3(1.0, 0.95, 0.8);
  float l = dot(col, vec3(.299,.587,.114));
  col = mix(vec3(l), col, 1.0 + sat);
  if(rainbow > 0.){
    vec3 rb = hue(fract(uv.x*0.6 + uv.y*0.4 - time*0.6));
    col = mix(col, col*(0.6+rb*0.9), rainbow*0.45);
  }
  col += flash;
  float v = 1.0 - dot(c,c) * vig;
  col *= v;
  gl_FragColor = vec4(col, 1.);
}`;

  GL.init = function (canvas) {
    let gl = null;
    try { gl = canvas.getContext('webgl', { antialias: false, alpha: false, premultipliedAlpha: false, preserveDrawingBuffer: false }); } catch (e) { gl = null; }
    if (!gl) return false;
    function sh(type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn(gl.getShaderInfoLog(s)); return null; } return s; }
    const vs = sh(gl.VERTEX_SHADER, VS), fs = sh(gl.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return false;
    const pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { console.warn(gl.getProgramInfoLog(pr)); return false; }
    gl.useProgram(pr);
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    const U = {};
    ['tex', 'res', 'time', 'aberr', 'sat', 'rainbow', 'flash', 'vig', 'pix', 'rip'].forEach(n => { U[n] = gl.getUniformLocation(pr, n); });
    GL.gl = gl; GL.tex = tex; GL.U = U; GL.canvas = canvas; GL.ok = true;
    canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); GL.ok = false; });
    return true;
  };

  // params: {time, aberr, sat, rainbow, flash, ripples:[{x,y,r,s}] in uv coords}
  GL.render = function (scene, p) {
    const gl = GL.gl, U = GL.U, cv = GL.canvas;
    if (cv.width !== scene.width || cv.height !== scene.height) { cv.width = scene.width; cv.height = scene.height; }
    gl.viewport(0, 0, cv.width, cv.height);
    gl.bindTexture(gl.TEXTURE_2D, GL.tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, scene);
    gl.uniform1i(U.tex, 0);
    gl.uniform2f(U.res, cv.width, cv.height);
    gl.uniform1f(U.time, p.time); gl.uniform1f(U.aberr, p.aberr); gl.uniform1f(U.sat, p.sat);
    gl.uniform1f(U.rainbow, p.rainbow); gl.uniform1f(U.flash, p.flash); gl.uniform1f(U.vig, p.vig == null ? 0.55 : p.vig);
    const a = new Float32Array(16);
    for (let i = 0; i < 4; i++) { const r = p.ripples[i]; if (r) { a[i * 4] = r.x; a[i * 4 + 1] = r.y; a[i * 4 + 2] = r.r; a[i * 4 + 3] = r.s; } }
    gl.uniform4fv(U.rip, a);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };
})(window);
