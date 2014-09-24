/*
 Command-line option parser.

 Copyright (C) 2014 AMPL Optimization Inc

 Permission to use, copy, modify, and distribute this software and its
 documentation for any purpose and without fee is hereby granted,
 provided that the above copyright notice appear in all copies and that
 both that the copyright notice and this permission notice and warranty
 disclaimer appear in supporting documentation.

 The author and AMPL Optimization Inc disclaim all warranties with
 regard to this software, including all implied warranties of
 merchantability and fitness.  In no event shall the author be liable
 for any special, indirect or consequential damages or any damages
 whatsoever resulting from loss of use, data or profits, whether in an
 action of contract, negligence or other tortious action, arising out
 of or in connection with the use or performance of this software.

 Author: Victor Zverovich
 */

#include "mp/option.h"

#include <algorithm>
#include <cctype>

using mp::Option;

namespace {

struct OptionLess {
  bool operator()(const Option &lhs, const Option &rhs) const {
    return lhs.name < rhs.name;
  }
  bool operator()(const Option &lhs, char rhs) const { return lhs.name < rhs; }
  bool operator()(char lhs, const Option &rhs) const { return lhs < rhs.name; }
};

std::string MakePrintable(char c) {
  return std::isprint(c) ? std::string(1, c) : fmt::format("\\x{:02d}", c);
}
}  // namespace

void mp::OptionList::Sort() {
  if (sorted_) return;
  std::sort(options_.begin(), options_.end(), OptionLess());
  sorted_ = true;
}

const Option *mp::OptionList::Find(char name) const {
  OptionContainer::const_iterator it =
      std::lower_bound(options_.begin(), options_.end(), name, OptionLess());
  return it != options_.end() && it->name == name ? &*it : 0;
}

char **mp::ParseOptions(char **args, OptionList &options) {
  options.Sort();
  char **arg_ptr = args;
  for (; *arg_ptr; ++arg_ptr) {
    const char *arg = *arg_ptr;
    if (*arg != '-')
      break;
    char name = arg[1];
    const Option *opt = options.Find(name);
    if (!opt) {
      throw OptionError(
            fmt::format("invalid option '-{}'", MakePrintable(name)));
    }
    if (!opt->on_option(opt->handler))
      break;
  }
  return arg_ptr;
}

// TODO: test
