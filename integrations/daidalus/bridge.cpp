// Streaming adapter between dense-uav-ops and NASA DAIDALUS (MIT license).
// DAIDALUS itself is NASA software under the NASA Open Source Agreement; it is
// downloaded and built separately by scripts/build_daidalus.py and is not
// redistributed by this repository.
//
// Protocol (one frame per request, any number of frames per process):
//   input : "<count> <time>" then <count> lines "<id> <x> <y> <z> <vx> <vy> <vz>"
//           in SI units, local east-north-up metres. The first aircraft is ownship.
//   output: one JSON line with per-traffic alert levels and horizontal direction
//           bands (degrees clockwise from north).
// One DAIDALUS object is kept per ownship id so hysteresis and persistence
// logic see that ownship's own history.
#include "Daidalus.h"
#include "BandsRegion.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
using namespace larcfm;

static void number(double x) {
  if (std::isfinite(x)) std::cout << x; else std::cout << "null";
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  const std::string configuration(argv[1]);
  {
    Daidalus probe;
    if (!probe.loadFromFile(configuration)) return 3;
  }
  std::map<int, std::unique_ptr<Daidalus>> instances;
  std::cout << std::setprecision(17);
  int n; double time;
  while (std::cin >> n >> time) {
    if (n < 1 || n > 5000 || !std::isfinite(time)) return 4;
    std::set<int> ids;
    int own = -1;
    Daidalus *daa = nullptr;
    for (int k = 0; k < n; ++k) {
      int id; double x, y, z, vx, vy, vz;
      if (!(std::cin >> id >> x >> y >> z >> vx >> vy >> vz) || !ids.insert(id).second) return 4;
      for (double v : {x, y, z, vx, vy, vz}) if (!std::isfinite(v)) return 4;
      Position p = Position::mkXYZ(x, y, z);
      Velocity v = Velocity::mkVxyz(vx, vy, vz);
      if (k == 0) {
        own = id;
        auto &slot = instances[id];
        if (!slot) {
          slot.reset(new Daidalus());
          if (!slot->loadFromFile(configuration)) return 3;
        }
        daa = slot.get();
        daa->setOwnshipState(std::to_string(id), p, v, time);
      } else {
        daa->addTrafficState(std::to_string(id), p, v, time);
      }
    }
    std::cout << "{\"own\":" << own << ",\"alerts\":[";
    for (int k = 1; k < n; ++k) {
      if (k > 1) std::cout << ",";
      std::cout << "[" << daa->getAircraftStateAt(k).getId() << "," << daa->alertLevel(k) << "]";
    }
    std::cout << "],\"bands\":[";
    for (int k = 0; k < daa->horizontalDirectionBandsLength(); ++k) {
      if (k) std::cout << ",";
      Interval b = daa->horizontalDirectionIntervalAt(k, "deg");
      std::cout << "[";
      number(b.low);
      std::cout << ",";
      number(b.up);
      std::cout << ",\"" << BandsRegion::to_string(daa->horizontalDirectionRegionAt(k)) << "\"]";
    }
    std::cout << "]}" << std::endl;
  }
  return 0;
}
