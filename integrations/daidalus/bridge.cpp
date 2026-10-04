// Original MIT adapter. NASA's library remains separately licensed under NOSA.
#include "Daidalus.h"
#include "BandsRegion.h"
#include <iostream>
#include <iomanip>
#include <cmath>
#include <set>
using namespace larcfm;
static void number(double x) {
  if (std::isfinite(x)) std::cout << x; else std::cout << "null";
}
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  Daidalus daa;
  if (!daa.loadFromFile(argv[1])) return 3;
  int n; double time;
  if (!(std::cin >> n >> time) || n < 1 || n > 2000 || !std::isfinite(time)) return 4;
  std::set<int> ids;
  for (int k=0; k<n; ++k) {
    int id; double x,y,z,vx,vy,vz;
    if (!(std::cin>>id>>x>>y>>z>>vx>>vy>>vz) || !ids.insert(id).second) return 4;
    for (double v : {x,y,z,vx,vy,vz}) if (!std::isfinite(v)) return 4;
    Position p=Position::mkXYZ(x,y,z); Velocity v=Velocity::mkVxyz(vx,vy,vz);
    if (!k) daa.setOwnshipState(std::to_string(id),p,v,time);
    else daa.addTrafficState(std::to_string(id),p,v,time);
  }
  std::cout<<std::setprecision(17)<<"{\"alerts\":[";
  for (int k=1;k<n;++k) {
    if (k>1) std::cout<<",";
    std::cout<<"{\"id\":\""<<daa.getAircraftStateAt(k).getId()<<"\",\"level\":"<<daa.alertLevel(k)<<"}";
  }
  std::cout<<"],\"direction_bands_deg\":[";
  for (int k=0;k<daa.horizontalDirectionBandsLength();++k) {
    if (k) std::cout<<",";
    Interval b=daa.horizontalDirectionIntervalAt(k,"deg");
    std::cout<<"{\"low\":";number(b.low);std::cout<<",\"high\":";number(b.up);
    std::cout<<",\"region\":\""<<BandsRegion::to_string(daa.horizontalDirectionRegionAt(k))<<"\"}";
  }
  std::cout<<"],\"right_resolution_deg\":";number(daa.horizontalDirectionResolution(true,"deg"));
  std::cout<<",\"left_resolution_deg\":";number(daa.horizontalDirectionResolution(false,"deg"));
  std::cout<<",\"scope\":\"snapshot advisory; constant-velocity traffic; no hysteresis history\"}\n";
}
