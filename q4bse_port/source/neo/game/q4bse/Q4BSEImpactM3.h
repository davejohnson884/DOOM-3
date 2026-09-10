#ifndef __Q4BSE_IMPACT_M3_H__
#define __Q4BSE_IMPACT_M3_H__

// M3 full HyperBlaster impact vertical slice.  This stays entirely inside the
// normal Doom 3 GPL Game DLL and uses only public Game/render/sound interfaces.
void Q4BSE_M3_Init(void);
void Q4BSE_M3_Shutdown(void);
void Q4BSE_M3_BeginMap(void);
void Q4BSE_M3_EndMap(void);
void Q4BSE_M3_Frame(int gameTimeMS);

#endif
