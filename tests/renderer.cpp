// Exercise the actual D3D8/WebGL implementation with framebuffer readback.
#include <d3d8.h>
#include <GLES3/gl3.h>
#include <emscripten.h>
#include <cstdio>
#include <cstring>

struct Vertex { float x,y,z; DWORD color; };
static IDirect3DDevice8* device;
static int failed = 0;
static void check(const char* name, unsigned char r, unsigned char g, unsigned char b) {
  unsigned char pixel[4] = {};
  glReadPixels(32,32,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
  const bool ok = pixel[0]==r && pixel[1]==g && pixel[2]==b;
  printf("%s %s (%u,%u,%u)\n",ok?"PASS":"FAIL",name,pixel[0],pixel[1],pixel[2]);
  if (!ok) ++failed;
}
static void triangle(float z, DWORD color, bool clockwise=false) {
  Vertex v[]={{-.9f,-.9f,z,color},{.9f,-.9f,z,color},{0,.9f,z,color}};
  if (clockwise) { auto t=v[0];v[0]=v[1];v[1]=t; }
  device->DrawPrimitiveUP(D3DPT_TRIANGLELIST,1,v,sizeof(Vertex));
}
static void clear() { device->Clear(0,nullptr,D3DCLEAR_TARGET|D3DCLEAR_ZBUFFER,0xff000000,1,0); }
int main() {
  auto d3d=Direct3DCreate8(D3D_SDK_VERSION);
  D3DPRESENT_PARAMETERS pp={};pp.BackBufferWidth=64;pp.BackBufferHeight=64;
  pp.BackBufferFormat=D3DFMT_A8R8G8B8;pp.Windowed=TRUE;pp.EnableAutoDepthStencil=TRUE;pp.AutoDepthStencilFormat=D3DFMT_D24S8;
  d3d->CreateDevice(0,D3DDEVTYPE_HAL,nullptr,0,&pp,&device);
  D3DVIEWPORT8 vp={0,0,64,64,0,1};device->SetViewport(&vp);
  device->SetVertexShader(D3DFVF_XYZ|D3DFVF_DIFFUSE);
  // Match the game: rely on Direct3D defaults, not explicit depth setters.
  device->SetRenderState(D3DRS_CULLMODE,D3DCULL_CW);
  clear();triangle(.5f,0xffff0000);check("CCW face visible, CW culled",255,0,0);
  clear();triangle(.5f,0xffff0000,true);check("CW face hidden",0,0,0);
  device->SetRenderState(D3DRS_CULLMODE,D3DCULL_NONE);
  clear();triangle(.2f,0xffff0000);triangle(.8f,0xff0000ff);check("near before far",255,0,0);
  clear();triangle(.8f,0xff0000ff);triangle(.2f,0xffff0000);check("far before near",255,0,0);
  // A far, sloping sky polygon must not overwrite nearer geometry due to bias.
  clear();triangle(.9f,0xffff0000);
  device->SetRenderState(D3DRS_ZBIAS,1);
  Vertex sky[]={{-.9f,-.9f,.99f,0xff0000ff},{.9f,-.9f,.99f,0xff0000ff},{0,.9f,.999f,0xff0000ff}};
  device->DrawPrimitiveUP(D3DPT_TRIANGLELIST,1,sky,sizeof(Vertex));
  check("sloped far surface with constant Z bias",255,0,0);
  device->SetRenderState(D3DRS_ZENABLE,FALSE);
  device->SetRenderState(D3DRS_ZWRITEENABLE,FALSE);
  device->Reset(&pp);
  device->SetRenderState(D3DRS_ZBIAS,0);
  clear();triangle(.2f,0xffff0000);triangle(.8f,0xff0000ff);check("reset restores default depth",255,0,0);
  pp.EnableAutoDepthStencil=FALSE;device->Reset(&pp);
  clear();triangle(.2f,0xffff0000);triangle(.8f,0xff0000ff);check("no automatic depth leaves test disabled",0,0,255);
  printf("RESULT: %d failures\n",failed);
  return failed;
}
