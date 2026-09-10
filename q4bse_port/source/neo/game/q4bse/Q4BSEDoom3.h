#ifndef __Q4BSE_DOOM3_H__
#define __Q4BSE_DOOM3_H__

// Source-level integration points for the stock Doom 3 GPL Game DLL.
// No wrappers, vtable patches, binary interception, or Phrozo dependency.

void Q4BSE_Init(void);
void Q4BSE_Shutdown(void);
void Q4BSE_BeginMap(void);
void Q4BSE_EndMap(void);
void Q4BSE_Frame(int gameTimeMS);

#endif
