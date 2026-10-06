// Exercise the selected real fb303 library; no daemon or sockets.
// Licensed under Apache-2.0; see LICENSE.
#include <FacebookBase.h>
#include <chrono>
#include <cstdlib>
#include <future>
#include <iostream>
#include <new>
#include <thread>
#include <vector>
#include <unistd.h>

static thread_local bool failNext = false;
extern "C" void* __real__Znwm(std::size_t);
extern "C" void* __wrap__Znwm(std::size_t size) {
  if (failNext) { failNext = false; throw std::bad_alloc(); }
  return __real__Znwm(size);
}
class Counters : public facebook::fb303::FacebookBase {
 public:
  Counters() : FacebookBase("fixture") {}
  facebook::fb303::fb_status getStatus() override { return facebook::fb303::ALIVE; }
};
static void require(bool value, const char* message) {
  if (!value) { std::cerr << message << std::endl; std::exit(3); }
}
int main(int argc, char** argv) {
  alarm(10);
  require(argc == 2, "one case required");
  Counters counters;
  const std::string mode(argv[1]);
  if (mode == "normal") {
    require(counters.getCounter("absent") == 0, "absent counter changed");
    require(counters.setCounter("signed", -3) == -3, "set return changed");
    require(counters.incrementCounter("signed", 2) == -1, "increment return changed");
    require(counters.incrementCounter("signed") == 0, "default amount changed");
    counters.setCounter("shared", 0);
    std::vector<std::thread> callers;
    for (int i = 0; i < 4; ++i) callers.emplace_back([&] {
      for (int j = 0; j < 500; ++j) counters.incrementCounter("shared");
    });
    for (auto& caller : callers) caller.join();
    std::map<std::string, int64_t> snapshot;
    counters.getCounters(snapshot);
    require(snapshot.size() == 2 && snapshot["signed"] == 0 && snapshot["shared"] == 2000,
            "normal counter/snapshot results changed");
  } else {
    counters.setCounter("existing", 7);
    std::map<std::string, int64_t> snapshot;
    bool threw = false;
    failNext = true;
    try {
      if (mode == "increment") counters.incrementCounter("fresh", 2);
      else if (mode == "set") counters.setCounter("fresh", 2);
      else { require(mode == "snapshot", "unknown case"); counters.getCounters(snapshot); }
    } catch (const std::bad_alloc&) { threw = true; }
    require(threw && !failNext, "real counter allocation failure not exercised");
    std::cout << "caught bad_alloc " << mode << std::endl;
    std::promise<void> completed;
    auto event = completed.get_future();
    std::thread recovery([&] {
      require(counters.getCounter("existing") == 7, "exception changed existing counter");
      require(counters.getCounter("fresh") == 0, "failed insertion published a counter");
      require(counters.incrementCounter("fresh", 3) == 3, "counter did not recover");
      completed.set_value();
    });
    require(event.wait_for(std::chrono::seconds(2)) == std::future_status::ready,
            "counter lock remains held after allocation exception");
    recovery.join();
  }
  std::cout << mode << ": PASS" << std::endl;
}
