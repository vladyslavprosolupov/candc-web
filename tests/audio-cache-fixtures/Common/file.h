#pragma once
extern unsigned int fixtureEncodedBytes;
class File {
public:
    unsigned int size() const { return fixtureEncodedBytes; }
};
