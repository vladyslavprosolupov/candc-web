// Drive more than 256 genuine shader states through the production GL wrapper.
#define main renderer_depth_tests
#include "renderer.cpp"
#undef main

static void expect(const char *name, bool ok) {
  printf("%s %s\n", ok ? "PASS" : "FAIL", name);
  if (!ok) ++failed;
}

static void state(unsigned value) {
  const DWORD args[] = {D3DTA_DIFFUSE, D3DTA_CURRENT, D3DTA_TFACTOR,
    D3DTA_DIFFUSE | D3DTA_COMPLEMENT, D3DTA_CURRENT | D3DTA_ALPHAREPLICATE,
    D3DTA_TFACTOR | D3DTA_COMPLEMENT};
  const D3DTEXTURESTAGESTATETYPE slots[] = {D3DTSS_COLORARG1, D3DTSS_COLORARG2, D3DTSS_ALPHAARG1, D3DTSS_ALPHAARG2};
  for (auto slot : slots) {
    device->SetTextureStageState(0, slot, args[value % 6]);
    value /= 6;
  }
  triangle(.5f, 0xffff0000);
}

int main() {
  renderer_depth_tests();
  device->SetRenderState(D3DRS_ZENABLE, FALSE);
  device->SetRenderState(D3DRS_TEXTUREFACTOR, 0xffffffff);
  IDirect3DTexture8 *tex = nullptr;
  device->CreateTexture(1, 1, 1, 0, D3DFMT_A8R8G8B8, D3DPOOL_DEFAULT, &tex);
  D3DLOCKED_RECT lock;
  tex->LockRect(0, &lock, nullptr, 0); *static_cast<DWORD *>(lock.pBits) = 0xffffffff; tex->UnlockRect(0);
  device->SetTexture(0, tex); tex->Release();
  device->SetTextureStageState(0, D3DTSS_COLOROP, D3DTOP_MODULATE);
  device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_MODULATE);
  state(0);
  GLint oldest = 0;
  glGetIntegerv(GL_CURRENT_PROGRAM, &oldest);
  for (unsigned value = 1; value < 300; ++value) state(value);
  expect("shader cache owns at most 256 live GL programs", EM_ASM_INT({ return GL.programs.filter(Boolean).length; }) <= 256);
  expect("least recently used shader program is retired", !glIsProgram(oldest));
  GLint current = 0, again = 0;
  glGetIntegerv(GL_CURRENT_PROGRAM, &current);
  state(299);
  glGetIntegerv(GL_CURRENT_PROGRAM, &again);
  expect("recent shader cache hit reuses its live program", current == again && glIsProgram(again));
  // The pre-fix overflow path leaks another program every time this exact
  // same state is drawn, because overflow entries never enter the cache.
  for (int draw = 0; draw < 20; ++draw) state(299);
  expect("overflow-state redraw does not accumulate programs", EM_ASM_INT({ return GL.programs.filter(Boolean).length; }) <= 256);
  device->SetTextureStageState(0, D3DTSS_COLOROP, D3DTOP_SELECTARG2);
  device->SetTextureStageState(0, D3DTSS_COLORARG2, D3DTA_DIFFUSE);
  device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_SELECTARG2);
  device->SetTextureStageState(0, D3DTSS_ALPHAARG2, D3DTA_DIFFUSE);
  clear(); triangle(.5f, 0xffff0000);
  check("ordinary draw after shader eviction", 255, 0, 0);
  expect("shader eviction leaves no GL errors", glGetError() == GL_NO_ERROR);
  device->SetTexture(0, nullptr); device->Release();
  printf("PROGRAM RESULT: %d failures\n", failed);
  return failed;
}
