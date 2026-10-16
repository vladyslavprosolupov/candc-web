// Actual production-wrapper lifetime tests; inspect live GL objects, not source patterns.
#define main renderer_depth_tests
#include "renderer.cpp"
#undef main

static void expect(const char *name, bool ok) {
  printf("%s %s\n", ok ? "PASS" : "FAIL", name);
  if (!ok) ++failed;
}

static IDirect3DTexture8 *texture() {
  IDirect3DTexture8 *tex = nullptr;
  device->CreateTexture(4, 4, 1, 0, D3DFMT_A8R8G8B8, D3DPOOL_DEFAULT, &tex);
  D3DLOCKED_RECT lock;
  tex->LockRect(0, &lock, nullptr, 0);
  for (int row = 0; row < 4; ++row)
    for (int col = 0; col < 4; ++col)
      reinterpret_cast<DWORD *>(static_cast<BYTE *>(lock.pBits) + row * lock.Pitch)[col] = 0xffff0000;
  tex->UnlockRect(0);
  return tex;
}

static void boundRenderTargetLifetime(const char *ending) {
  IDirect3DSurface8 *back = nullptr, *level = nullptr;
  device->GetBackBuffer(0, D3DBACKBUFFER_TYPE_MONO, &back);
  auto tex = texture();
  tex->GetSurfaceLevel(0, &level);
  device->SetRenderTarget(level, nullptr);
  level->Release();
  // Only the device now owns the texture. Rebinding its current surface must
  // acquire the replacement owner reference before dropping the previous one.
  expect("bound target retains its parent texture", tex->Release() == 1);
  device->GetRenderTarget(&level);
  device->SetRenderTarget(level, nullptr);
  D3DSURFACE_DESC desc;
  expect("bound level remains valid after caller releases texture", level->GetDesc(&desc) == D3D_OK && desc.Width == 4);
  level->Release();
  clear(); triangle(.5f, 0xffff0000);
  expect("draw into bound target after parent release", glGetError() == GL_NO_ERROR);
  if (strcmp(ending, "reset") == 0) {
    D3DPRESENT_PARAMETERS pp = {};
    pp.BackBufferWidth = pp.BackBufferHeight = 64;
    pp.BackBufferFormat = D3DFMT_A8R8G8B8; pp.Windowed = TRUE;
    device->Reset(&pp);
  } else {
    device->SetRenderTarget(back, nullptr);
  }
  back->Release();
  GLint binding = -1;
  glGetIntegerv(GL_FRAMEBUFFER_BINDING, &binding);
  expect(ending, binding == 0 && glGetError() == GL_NO_ERROR);
}

int main() {
  renderer_depth_tests();
  device->SetRenderState(D3DRS_ZENABLE, FALSE);
  device->SetTextureStageState(0, D3DTSS_COLOROP, D3DTOP_SELECTARG1);
  device->SetTextureStageState(0, D3DTSS_COLORARG1, D3DTA_TEXTURE);
  // Repeat allocation/upload/final Release: the pre-fix wrapper leaves every
  // recorded GL object alive even though its D3D resource has been destroyed.
  for (int cycle = 0; cycle < 16; ++cycle) {
    auto tex = texture();
    device->SetTexture(0, tex);
    triangle(.5f, 0xffffffff);
    GLint name = 0;
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &name);
    // bindTextures finishes on stage 1, so query the texture's actual stage.
    glActiveTexture(GL_TEXTURE0);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &name);
    expect("uploaded texture is live", name != 0 && glIsTexture(name));
    tex->Release();
    expect("device binding retains texture", glIsTexture(name));
    device->SetTexture(0, nullptr);
    expect("final texture Release deletes GL texture", !glIsTexture(name));

    IDirect3DVertexBuffer8 *vb = nullptr;
    IDirect3DIndexBuffer8 *ib = nullptr;
    device->CreateVertexBuffer(3 * sizeof(Vertex), 0, D3DFVF_XYZ | D3DFVF_DIFFUSE, D3DPOOL_DEFAULT, &vb);
    device->CreateIndexBuffer(3 * sizeof(WORD), 0, D3DFMT_INDEX16, D3DPOOL_DEFAULT, &ib);
    BYTE *bits;
    Vertex vertices[] = {{-.9f,-.9f,.5f,0xffff0000},{.9f,-.9f,.5f,0xffff0000},{0,.9f,.5f,0xffff0000}};
    WORD indices[] = {0,1,2};
    vb->Lock(0, sizeof(vertices), &bits, 0); memcpy(bits, vertices, sizeof(vertices)); vb->Unlock();
    ib->Lock(0, sizeof(indices), &bits, 0); memcpy(bits, indices, sizeof(indices)); ib->Unlock();
    device->SetStreamSource(0, vb, sizeof(Vertex)); device->SetIndices(ib, 0);
    device->DrawIndexedPrimitive(D3DPT_TRIANGLELIST, 0, 3, 0, 1);
    GLint vertexName = 0, indexName = 0;
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &vertexName);
    glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING, &indexName);
    vb->Release(); ib->Release();
    expect("device binding retains uploaded buffers", glIsBuffer(vertexName) && glIsBuffer(indexName));
    device->SetStreamSource(0, nullptr, 0); device->SetIndices(nullptr, 0);
    expect("final vertex/index Release deletes GL buffers", !glIsBuffer(vertexName) && !glIsBuffer(indexName));

    tex = texture();
    IDirect3DSurface8 *level = nullptr, *back = nullptr;
    tex->GetSurfaceLevel(0, &level);
    device->GetBackBuffer(0, D3DBACKBUFFER_TYPE_MONO, &back);
    device->SetRenderTarget(level, nullptr);
    GLint fbo = 0, targetTexture = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &fbo);
    glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME, &targetTexture);
    expect("render-target texture and FBO are live", glIsFramebuffer(fbo) && glIsTexture(targetTexture));
    device->SetRenderTarget(back, nullptr);
    back->Release(); level->Release(); tex->Release();
    expect("final target Release deletes texture and FBO", !glIsFramebuffer(fbo) && !glIsTexture(targetTexture));
  }
  boundRenderTargetLifetime("unbind restores backbuffer");
  boundRenderTargetLifetime("reset");
  // Resources never uploaded have no GL ownership to retire.
  texture()->Release();
  expect("resource cleanup leaves no GL errors", glGetError() == GL_NO_ERROR);

  auto target = texture();
  IDirect3DSurface8 *level = nullptr;
  target->GetSurfaceLevel(0, &level);
  device->SetRenderTarget(level, nullptr);
  GLint fbo = 0, targetName = 0;
  glGetIntegerv(GL_FRAMEBUFFER_BINDING, &fbo);
  glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME, &targetName);
  level->Release(); target->Release();
  device->Release();
  expect("device destruction releases its bound target", !glIsFramebuffer(fbo) && !glIsTexture(targetName));
  expect("device destruction restores canvas target", EM_ASM_INT({ return GLctx.getParameter(GLctx.FRAMEBUFFER_BINDING) === null; }));
  printf("RESOURCE RESULT: %d failures\n", failed);
  return failed;
}
