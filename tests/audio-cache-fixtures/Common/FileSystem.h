#pragma once
#include "Common/file.h"
class FixtureFileSystem {
public:
    File *openFile(const char *) { return new File(); }
};
extern FixtureFileSystem *TheFileSystem;
