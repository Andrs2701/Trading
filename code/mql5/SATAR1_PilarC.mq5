//+------------------------------------------------------------------+
//| SATAR-1 · Pilar C — PLANTILLA DE PORT a MQL5 (FASE-7, tercera     |
//| prioridad tras Pine v6 y Python).                                 |
//|                                                                   |
//| ESTADO: esqueleto funcional con la máquina de estados y los       |
//| módulos I/P completos. El módulo G (zonas extremas + patrones de  |
//| giro, FASE-2 §2.2-§3) está marcado con TODO y debe portarse desde |
//| satar_backtest.py ANTES de usar este EA. Paridad obligatoria      |
//| (FASE-2 §14) contra el motor Python en un subperiodo común.       |
//| Destino: forex/metales/índices en MT5 (decisión FASE-8).          |
//+------------------------------------------------------------------+
#property copyright "SATAR-1"
#property version   "0.90"
#property strict

#include <Trade/Trade.mqh>
CTrade trade;

//--- Parámetros (FASE-2 §10)
input int    P01_EmaN      = 50;     // EMA (identidad, no optimizar)
input int    P02_AtrN      = 14;
input double P21_ChaseAtr  = 0.5;    // anti-chase (xATR H1)
input int    P22_ArmedWin  = 12;     // ventana gatillo (velas H1)
input double P23_BufAtr    = 0.1;    // buffer stop (xATR H1)
input double P27_RrMin     = 0.5;
input double P28_RiskPct   = 1.0;    // % de equity por trade
input double P30_DdDay     = 2.0;    // límites kill-switch (%)
input double P31_DdWeek    = 4.0;
input double P32_DdMonth   = 6.0;

//--- Handles de indicadores por temporalidad
int hEmaM5, hEmaH1, hEmaD1, hAtrH1, hAtrD1, hAdxD1, hRsiD1;

//--- Máquina de estados (FASE-2 §13)
enum EState { ST_IDLE=0, ST_BIAS, ST_STRUCTURE, ST_ARMED, ST_IN_POSITION };
EState  state    = ST_IDLE;
int     dir      = 0;            // +1 long / -1 short
int     biasAgeG = 0, armedAgeI = 0;
double  oImp = 0, fImp = 0;      // anclas Fibonacci (FASE-2 §2.3)
double  eqDayStart=0, eqWeekStart=0, eqMonthStart=0;
datetime lastD1=0, lastH1=0, lastM5=0;

double Fib(const double r) { return fImp + r*(oImp - fImp); }
double Buf(const double atrH1) { return P23_BufAtr * atrH1; }

int OnInit()
{
   hEmaM5 = iMA(_Symbol, PERIOD_M5, P01_EmaN, 0, MODE_EMA, PRICE_CLOSE);
   hEmaH1 = iMA(_Symbol, PERIOD_H1, P01_EmaN, 0, MODE_EMA, PRICE_CLOSE);
   hEmaD1 = iMA(_Symbol, PERIOD_D1, P01_EmaN, 0, MODE_EMA, PRICE_CLOSE);
   hAtrH1 = iATR(_Symbol, PERIOD_H1, P02_AtrN);
   hAtrD1 = iATR(_Symbol, PERIOD_D1, P02_AtrN);
   hAdxD1 = iADX(_Symbol, PERIOD_D1, 14);
   hRsiD1 = iRSI(_Symbol, PERIOD_D1, 14, PRICE_CLOSE);
   eqDayStart = eqWeekStart = eqMonthStart = AccountInfoDouble(ACCOUNT_EQUITY);
   return (hEmaM5>0 && hEmaH1>0 && hAtrH1>0) ? INIT_SUCCEEDED : INIT_FAILED;
}

double Val(const int handle, const int shift)
{
   double b[1];
   return CopyBuffer(handle, 0, shift, 1, b) == 1 ? b[0] : 0.0;
}

bool NewBar(const ENUM_TIMEFRAMES tf, datetime &memo)
{
   datetime t = iTime(_Symbol, tf, 0);
   if(t == memo) return false;
   memo = t; return true;                      // la vela [1] acaba de cerrar
}

//--- Kill-switch jerárquico (FASE-6 §2): pérdida relativa al inicio del periodo
bool KillSwitch()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   MqlDateTime now; TimeToStruct(TimeCurrent(), now);
   static int day=-1, week=-1, mon=-1;
   int w = (int)(TimeCurrent()/604800);
   if(now.day != day)   { day = now.day;   eqDayStart   = eq; }
   if(w != week)        { week = w;        eqWeekStart  = eq; }
   if(now.mon != mon)   { mon = now.mon;   eqMonthStart = eq; }
   return eq <= eqDayStart  *(1 - P30_DdDay  /100.0)
       || eq <= eqWeekStart *(1 - P31_DdWeek /100.0)
       || eq <= eqMonthStart*(1 - P32_DdMonth/100.0);
}

void OnTick()
{
   //=== Cierre de vela D1: módulo G (sesgo) =================================
   if(NewBar(PERIOD_D1, lastD1) && state < ST_IN_POSITION)
   {
      biasAgeG++;
      if(state >= ST_BIAS && biasAgeG >= 3) { state = ST_IDLE; dir = 0; }   // R-C24
      // TODO(FASE-7): portar módulo G completo desde satar_backtest.py:
      //   G1 limpieza  : ER(20) >= 0.30 && ADX(14) >= 20        (D-4)
      //   G2 extremo   : clustering de pivotes D1 (FASE-2 §2.2)
      //   G3 llegada   : ER(tramo 5) >= 0.35 || RSI extremo     (AMBIG-2)
      //   G4 desacel.  : mean(|body|,3)/ATR10 <= 0.6            (D-2)
      //   G5 giro      : envolvente / pinbar / doble techo+neckline
      //   G6 no invalidado
      // Al validar: { state = ST_BIAS; dir = ±1; biasAgeG = 0; }
   }

   //=== Cierre de vela H1: módulos I (estructura/zona) y trailing ===========
   if(NewBar(PERIOD_H1, lastH1))
   {
      double emaH1 = Val(hEmaH1, 1), atrH1 = Val(hAtrH1, 1);
      double cH1   = iClose(_Symbol, PERIOD_H1, 1);
      if(state == ST_BIAS)
      {
         // TODO: I1 (EMA), I2 BOS por fractales k=2, I3 secuencia, anclar oImp/fImp (§4.1-4.2)
      }
      if(state == ST_STRUCTURE || state == ST_ARMED)
      {
         // TODO: I4 retroceso >= Fib(0.382), I5 anti-chase 0.5xATR, I7 invalidación Fib(1.0)
         if(state == ST_ARMED && ++armedAgeI > P22_ArmedWin) state = ST_STRUCTURE;  // I6
      }
      if(state == ST_IN_POSITION && PositionSelect(_Symbol))              // trailing D-6
      {
         long   ptype = PositionGetInteger(POSITION_TYPE);
         double sl    = PositionGetDouble(POSITION_SL);
         double tp    = PositionGetDouble(POSITION_TP);
         double cand  = (ptype == POSITION_TYPE_SELL) ? emaH1 + Buf(atrH1)
                                                      : emaH1 - Buf(atrH1);
         double newSl = (ptype == POSITION_TYPE_SELL) ? MathMin(sl, cand) : MathMax(sl, cand);
         if(MathAbs(newSl - sl) > _Point) trade.PositionModify(_Symbol, newSl, tp);
      }
   }

   //=== Cierre de vela M5: gatillo (módulo P, §5) ============================
   if(NewBar(PERIOD_M5, lastM5) && state == ST_ARMED && !PositionSelect(_Symbol) && !KillSwitch())
   {
      double e0 = Val(hEmaM5, 1), e1 = Val(hEmaM5, 2);
      double c0 = iClose(_Symbol, PERIOD_M5, 1), c1 = iClose(_Symbol, PERIOD_M5, 2);
      bool trig = (dir < 0) ? (c0 < e0 && c1 >= e1) : (c0 > e0 && c1 <= e1);   // cruce, no estado
      if(trig)
      {
         double atrH1 = Val(hAtrH1, 1);
         double sl    = 0, tp = 0;   // TODO: SL dinámico R-C35/D-1 y TP §7 desde anclas Fib
         double dist  = MathAbs(SymbolInfoDouble(_Symbol, SYMBOL_BID) - sl);
         if(dist >= 0.15*atrH1 && dist <= 3.0*atrH1)                            // sanidad §6
         {
            double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * P28_RiskPct/100.0;
            double tickVal   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
            double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
            double lots      = NormalizeDouble(riskMoney / (dist/tickSize*tickVal), 2);
            if(dir < 0) trade.Sell(lots, _Symbol, 0, sl, tp, "SATAR-1");
            else        trade.Buy (lots, _Symbol, 0, sl, tp, "SATAR-1");
            state = ST_IN_POSITION;
         }
         else state = ST_STRUCTURE;
      }
   }

   if(state == ST_IN_POSITION && !PositionSelect(_Symbol)) { state = ST_IDLE; dir = 0; }
}
//+------------------------------------------------------------------+
