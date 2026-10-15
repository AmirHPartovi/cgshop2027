#include "algorithms/TourConstruction.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <functional>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <random>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace cgshop2027 {
namespace {

constexpr Point kNeighbor[4] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

struct DSU {
    std::vector<int> parent;
    std::vector<int> rank;
    explicit DSU(int n) : parent(static_cast<size_t>(n)), rank(static_cast<size_t>(n), 0) {
        std::iota(parent.begin(), parent.end(), 0);
    }
    int find(int x) {
        if (parent[static_cast<size_t>(x)] != x)
            parent[static_cast<size_t>(x)] = find(parent[static_cast<size_t>(x)]);
        return parent[static_cast<size_t>(x)];
    }
    bool join(int a, int b) {
        a = find(a);
        b = find(b);
        if (a == b) return false;
        if (rank[static_cast<size_t>(a)] < rank[static_cast<size_t>(b)]) std::swap(a, b);
        parent[static_cast<size_t>(b)] = a;
        if (rank[static_cast<size_t>(a)] == rank[static_cast<size_t>(b)])
            ++rank[static_cast<size_t>(a)];
        return true;
    }
};

void appendStep(std::vector<Point>& path, Point to) {
    if (path.empty()) {
        path.push_back(to);
        return;
    }
    const Point from = path.back();
    if (from == to) return;
    if (from.x != to.x && from.y != to.y) path.push_back({to.x, from.y});
    path.push_back(to);
}

std::vector<Point> uniqueConsecutive(std::vector<Point> points) {
    points.erase(std::unique(points.begin(), points.end()), points.end());
    return points;
}

std::unordered_map<Point, int, PointHash> indexMap(const std::vector<Point>& anchors) {
    std::unordered_map<Point, int, PointHash> index;
    index.reserve(anchors.size() * 2U);
    for (size_t i = 0; i < anchors.size(); ++i) index[anchors[i]] = static_cast<int>(i);
    return index;
}

std::vector<std::vector<int>> spanningTree(const std::vector<Point>& anchors) {
    const int n = static_cast<int>(anchors.size());
    std::vector<std::vector<int>> adj(static_cast<size_t>(n));
    if (n <= 1) return adj;
    const auto index = indexMap(anchors);
    DSU dsu(n);
    int edges = 0;
    for (int i = 0; i < n; ++i) {
        for (const Point delta : kNeighbor) {
            const auto found = index.find(anchors[static_cast<size_t>(i)] + delta);
            if (found == index.end() || found->second <= i) continue;
            if (dsu.join(i, found->second)) {
                adj[static_cast<size_t>(i)].push_back(found->second);
                adj[static_cast<size_t>(found->second)].push_back(i);
                ++edges;
            }
        }
    }
    if (edges >= n - 1) return adj;
    std::vector<int> representative(static_cast<size_t>(n), -1);
    for (int i = 0; i < n; ++i) {
        const int root = dsu.find(i);
        int& rep = representative[static_cast<size_t>(root)];
        if (rep < 0 || anchors[static_cast<size_t>(i)] < anchors[static_cast<size_t>(rep)])
            rep = i;
    }
    std::vector<int> comps;
    for (int i = 0; i < n; ++i)
        if (representative[static_cast<size_t>(i)] >= 0)
            comps.push_back(representative[static_cast<size_t>(i)]);
    std::sort(comps.begin(), comps.end(), [&](int a, int b) {
        return anchors[static_cast<size_t>(a)] < anchors[static_cast<size_t>(b)];
    });
    for (size_t i = 1; i < comps.size(); ++i) {
        const int a = comps[i - 1];
        const int b = comps[i];
        if (dsu.join(a, b)) {
            adj[static_cast<size_t>(a)].push_back(b);
            adj[static_cast<size_t>(b)].push_back(a);
        }
    }
    return adj;
}

std::vector<Point> walkTree(const std::vector<Point>& anchors,
                            const std::vector<std::vector<int>>& adj, int root) {
    std::vector<Point> walk;
    if (anchors.empty()) return walk;
    std::function<void(int, int)> dfs = [&](int u, int parent) {
        appendStep(walk, anchors[static_cast<size_t>(u)]);
        for (int v : adj[static_cast<size_t>(u)]) {
            if (v == parent) continue;
            dfs(v, u);
            appendStep(walk, anchors[static_cast<size_t>(u)]);
        }
    };
    dfs(root, -1);
    return TourConstruction::compactPath(walk);
}

int interpolate(int a, int b, int step, int length) {
    if (length == 0) return a;
    return a + (b - a) * step / length;
}

Point pointAt(const std::vector<Point>& tour, int distance) {
    if (tour.empty()) return {};
    if (tour.size() == 1U) return tour.front();
    const int total = TourConstruction::closedLength(tour);
    if (total <= 0) return tour.front();
    distance %= total;
    if (distance < 0) distance += total;
    int acc = 0;
    for (size_t i = 0; i < tour.size(); ++i) {
        const Point a = tour[i];
        const Point b = tour[(i + 1) % tour.size()];
        const int length = a.manhattanDistance(b);
        if (acc + length >= distance) {
            const int step = distance - acc;
            return {interpolate(a.x, b.x, step, length),
                    interpolate(a.y, b.y, step, length)};
        }
        acc += length;
    }
    return tour.front();
}

std::vector<Point> subpath(const std::vector<Point>& tour, int startDistance,
                           int endDistance) {
    std::vector<Point> result;
    if (tour.empty()) return result;
    const int total = TourConstruction::closedLength(tour);
    if (total <= 0) return {tour.front()};
    startDistance %= total;
    if (startDistance < 0) startDistance += total;
    int span = endDistance - startDistance;
    if (span <= 0) span += total;
    result.push_back(pointAt(tour, startDistance));
    int acc = 0;
    for (size_t i = 0; i < tour.size(); ++i) {
        const Point a = tour[i];
        const Point b = tour[(i + 1) % tour.size()];
        const int length = a.manhattanDistance(b);
        const int vertexDistance = (acc + length) % total;
        int offset = vertexDistance - startDistance;
        if (offset < 0) offset += total;
        if (offset > 0 && offset < span) result.push_back(b);
        acc += length;
    }
    result.push_back(pointAt(tour, startDistance + span));
    return TourConstruction::compactPath(result);
}

std::map<int, std::vector<Point>> columnsOf(const std::vector<Point>& anchors) {
    std::map<int, std::vector<Point>> columns;
    for (const Point point : anchors) columns[point.x].push_back(point);
    for (auto& entry : columns)
        std::sort(entry.second.begin(), entry.second.end());
    return columns;
}

std::vector<Point> boustrophedonColumns(const std::map<int, std::vector<Point>>& columns) {
    std::vector<Point> path;
    bool downward = true;
    for (const auto& entry : columns) {
        if (entry.second.empty()) continue;
        Point low = entry.second.front();
        Point high = entry.second.back();
        low.x = entry.first;
        high.x = entry.first;
        if (downward) {
            appendStep(path, low);
            appendStep(path, high);
        } else {
            appendStep(path, high);
            appendStep(path, low);
        }
        downward = !downward;
    }
    return TourConstruction::compactPath(path);
}

int twoOptCycle(std::vector<int>& order,
                const std::vector<Point>& anchors,
                const std::chrono::steady_clock::time_point& start, double limit) {
    const int n = static_cast<int>(order.size());
    if (n < 4) return 0;
    auto dist = [&](int i, int j) {
        return anchors[static_cast<size_t>(order[static_cast<size_t>(i)])].manhattanDistance(
            anchors[static_cast<size_t>(order[static_cast<size_t>((j + n) % n)])]);
    };
    int passes = 0;
    bool improved = true;
    while (improved && passes < 12 && !TourConstruction::timedOut(start, limit)) {
        improved = false;
        ++passes;
        for (int i = 0; i < n && !TourConstruction::timedOut(start, limit); ++i) {
            for (int j = i + 2; j < n && !TourConstruction::timedOut(start, limit); ++j) {
                if (i == 0 && j == n - 1) continue;
                const int before = dist(i, i + 1) + dist(j, j + 1);
                const int after =
                    anchors[static_cast<size_t>(order[static_cast<size_t>(i)])]
                        .manhattanDistance(
                            anchors[static_cast<size_t>(order[static_cast<size_t>(j)])]) +
                    anchors[static_cast<size_t>(order[static_cast<size_t>(i + 1)])]
                        .manhattanDistance(anchors[static_cast<size_t>(
                            order[static_cast<size_t>((j + 1) % n)])]);
                if (after < before) {
                    std::reverse(order.begin() + i + 1, order.begin() + j + 1);
                    improved = true;
                }
            }
        }
    }
    return passes;
}

}  // namespace

std::vector<Point> TourConstruction::rectilinearConnect(Point from, Point to) {
    std::vector<Point> path;
    appendStep(path, from);
    appendStep(path, to);
    return compactPath(path);
}

std::vector<Point> TourConstruction::coveringAnchors(const Problem& problem) {
    const auto cells = problem.regionCells();
    const auto cutter = problem.cutterCells();
    std::vector<Point> result;
    if (cutter.empty()) return result;
    const Point anchor = *std::min_element(cutter.begin(), cutter.end());
    result.reserve(cells.size());
    for (const Point cell : cells)
        result.push_back({cell.x + problem.cutterCenter.x - anchor.x,
                          cell.y + problem.cutterCenter.y - anchor.y});
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    return result;
}

std::vector<Point> TourConstruction::compactPath(std::vector<Point> points) {
    points = uniqueConsecutive(std::move(points));
    if (points.size() < 3U) return points;
    std::vector<Point> compact;
    compact.push_back(points.front());
    for (size_t i = 1; i + 1 < points.size(); ++i) {
        const Point a = compact.back();
        const Point b = points[i];
        const Point c = points[i + 1];
        if ((a.x == b.x && b.x == c.x) || (a.y == b.y && b.y == c.y)) continue;
        compact.push_back(b);
    }
    compact.push_back(points.back());
    return uniqueConsecutive(std::move(compact));
}

Solution TourConstruction::makeSolution(const Problem& problem,
                                        const std::vector<std::vector<Point>>& groups) {
    auto close = [](const std::vector<Point>& input) {
        Tour result;
        if (input.empty()) return result;
        if (input.size() == 1U) {
            result.points = input;
            return result;
        }
        result.points.push_back(input.front());
        for (size_t i = 1; i < input.size(); ++i) {
            const Point a = result.points.back();
            const Point b = input[i];
            if (a.x != b.x && a.y != b.y) result.points.push_back({b.x, a.y});
            result.points.push_back(b);
        }
        const Point first = input.front();
        const Point last = result.points.back();
        if (last.x != first.x && last.y != first.y)
            result.points.push_back({first.x, last.y});
        result.points = compactPath(result.points);
        if (result.points.size() > 1U && result.points.front() == result.points.back())
            result.points.pop_back();
        return result;
    };
    Solution solution;
    solution.contentType = "CGSHOP2027_Solution";
    solution.instanceUid = problem.instanceUid;
    solution.tours.reserve(static_cast<size_t>(problem.numberOfCutters));
    for (const auto& group : groups) solution.tours.push_back(close(group));
    while (solution.tours.size() < static_cast<size_t>(problem.numberOfCutters))
        solution.tours.push_back(close({{0, 0}}));
    if (solution.tours.size() > static_cast<size_t>(problem.numberOfCutters))
        solution.tours.resize(static_cast<size_t>(problem.numberOfCutters));
    return solution;
}

std::vector<Point> TourConstruction::boustrophedon(const std::vector<Point>& anchors) {
    return boustrophedonColumns(columnsOf(anchors));
}

std::vector<Point> TourConstruction::spanningTreeWalk(const std::vector<Point>& anchors) {
    if (anchors.empty()) return {};
    const auto tree = spanningTree(anchors);
    return walkTree(anchors, tree, 0);
}

std::vector<Point> TourConstruction::tspCov(
    const std::vector<Point>& anchors, const std::chrono::steady_clock::time_point& start,
    double limit) {
    if (anchors.size() <= 2U) return anchors;
    if (anchors.size() > 3500U || timedOut(start, limit)) return boustrophedon(anchors);
    std::vector<char> used(anchors.size(), 0);
    std::vector<int> order;
    order.reserve(anchors.size());
    int current = 0;
    used[0] = 1;
    order.push_back(0);
    for (size_t step = 1; step < anchors.size(); ++step) {
        if (timedOut(start, limit)) return boustrophedon(anchors);
        int best = -1;
        int bestDistance = std::numeric_limits<int>::max();
        for (size_t i = 0; i < anchors.size(); ++i) {
            if (used[i] != 0) continue;
            const int distance =
                anchors[static_cast<size_t>(current)].manhattanDistance(anchors[i]);
            if (best < 0 || distance < bestDistance ||
                (distance == bestDistance && anchors[i] < anchors[static_cast<size_t>(best)])) {
                best = static_cast<int>(i);
                bestDistance = distance;
            }
        }
        if (best < 0) break;
        used[static_cast<size_t>(best)] = 1;
        order.push_back(best);
        current = best;
    }
    twoOptCycle(order, anchors, start, limit);
    std::vector<Point> path;
    for (int index : order) appendStep(path, anchors[static_cast<size_t>(index)]);
    return compactPath(path);
}

std::vector<std::vector<Point>> TourConstruction::splitFrederickson(
    const std::vector<Point>& tour, int k) {
    std::vector<std::vector<Point>> groups(static_cast<size_t>(std::max(k, 0)));
    if (groups.empty()) return groups;
    if (tour.empty()) return groups;
    const int total = closedLength(tour);
    if (total <= 0 || k <= 1) {
        groups[0] = tour;
        return groups;
    }
    int cursor = 0;
    const int base = total / k;
    const int extra = total % k;
    for (int i = 0; i < k; ++i) {
        const int span = base + (i < extra ? 1 : 0);
        if (span <= 0) {
            groups[static_cast<size_t>(i)] = {pointAt(tour, cursor)};
        } else {
            groups[static_cast<size_t>(i)] = subpath(tour, cursor, cursor + span);
        }
        cursor += span;
    }
    return groups;
}

std::vector<std::vector<Point>> TourConstruction::mstc(const std::vector<Point>& anchors,
                                                       int k) {
    const int n = static_cast<int>(anchors.size());
    const int cutters = std::max(k, 1);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
    if (n == 0) return groups;
    if (cutters == 1) {
        groups[0] = spanningTreeWalk(anchors);
        return groups;
    }
    auto adj = spanningTree(anchors);
    std::vector<char> blocked(static_cast<size_t>(n), 0);
    auto collect = [&](int root) {
        std::vector<int> nodes;
        std::function<void(int, int)> dfs = [&](int u, int p) {
            nodes.push_back(u);
            for (int v : adj[static_cast<size_t>(u)]) {
                if (v == p || blocked[static_cast<size_t>(v)] != 0) continue;
                dfs(v, u);
            }
        };
        dfs(root, -1);
        return nodes;
    };
    int remaining = n;
    for (int part = 0; part + 1 < cutters && remaining > 0; ++part) {
        int root = 0;
        while (root < n && blocked[static_cast<size_t>(root)] != 0) ++root;
        if (root >= n) break;
        std::vector<int> parent(static_cast<size_t>(n), -1);
        std::vector<int> size(static_cast<size_t>(n), 0);
        std::function<int(int, int)> calc = [&](int u, int p) {
            parent[static_cast<size_t>(u)] = p;
            int total = 1;
            for (int v : adj[static_cast<size_t>(u)]) {
                if (v == p || blocked[static_cast<size_t>(v)] != 0) continue;
                total += calc(v, u);
            }
            size[static_cast<size_t>(u)] = total;
            return total;
        };
        calc(root, -1);
        const int target = std::max(1, remaining / (cutters - part));
        int best = -1;
        int bestDiff = std::numeric_limits<int>::max();
        for (int u = 0; u < n; ++u) {
            if (blocked[static_cast<size_t>(u)] != 0 || u == root) continue;
            const int diff = std::abs(size[static_cast<size_t>(u)] - target);
            if (best < 0 || diff < bestDiff) {
                best = u;
                bestDiff = diff;
            }
        }
        if (best < 0) best = root;
        const std::vector<int> nodes = collect(best);
        std::vector<Point> subset;
        subset.reserve(nodes.size());
        for (int u : nodes) {
            blocked[static_cast<size_t>(u)] = 1;
            subset.push_back(anchors[static_cast<size_t>(u)]);
        }
        remaining -= static_cast<int>(nodes.size());
        groups[static_cast<size_t>(part)] = spanningTreeWalk(subset);
    }
    std::vector<Point> leftover;
    for (int u = 0; u < n; ++u)
        if (blocked[static_cast<size_t>(u)] == 0)
            leftover.push_back(anchors[static_cast<size_t>(u)]);
    groups.back() = leftover.empty() ? std::vector<Point>{} : spanningTreeWalk(leftover);
    return groups;
}

std::vector<std::vector<Point>> TourConstruction::recursiveBisectionTours(
    const std::vector<Point>& anchors, int k) {
    const int cutters = std::max(k, 1);
    std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
    if (anchors.empty()) return groups;
    std::function<void(std::vector<Point>, int, int)> split =
        [&](std::vector<Point> cells, int offset, int count) {
            if (count <= 1 || cells.empty()) {
                if (offset >= 0 && offset < cutters)
                    groups[static_cast<size_t>(offset)] = boustrophedon(cells);
                return;
            }
            const int leftCount = count / 2;
            const int rightCount = count - leftCount;
            int minX = cells.front().x, maxX = minX, minY = cells.front().y, maxY = minY;
            for (const Point point : cells) {
                minX = std::min(minX, point.x);
                maxX = std::max(maxX, point.x);
                minY = std::min(minY, point.y);
                maxY = std::max(maxY, point.y);
            }
            const bool vertical = (maxX - minX) >= (maxY - minY);
            std::sort(cells.begin(), cells.end(), [&](Point a, Point b) {
                return vertical ? (a.x < b.x || (a.x == b.x && a.y < b.y))
                                : (a.y < b.y || (a.y == b.y && a.x < b.x));
            });
            const size_t splitAt = static_cast<size_t>(cells.size()) * static_cast<size_t>(leftCount) /
                                   static_cast<size_t>(count);
            std::vector<Point> left(cells.begin(),
                                    cells.begin() + static_cast<std::ptrdiff_t>(splitAt));
            std::vector<Point> right(cells.begin() + static_cast<std::ptrdiff_t>(splitAt),
                                     cells.end());
            split(std::move(left), offset, leftCount);
            split(std::move(right), offset + leftCount, rightCount);
        };
    split(anchors, 0, cutters);
    return groups;
}

std::vector<std::vector<Point>> TourConstruction::stripIlpTours(
    const std::vector<Point>& anchors, int k) {
    const auto columns = columnsOf(anchors);
    const int cutters = std::max(k, 1);
    if (columns.empty()) return std::vector<std::vector<Point>>(static_cast<size_t>(cutters));
    std::vector<std::pair<int, std::vector<Point>>> strips(columns.begin(), columns.end());
    const int m = static_cast<int>(strips.size());
    if (cutters == 1 || m <= cutters) {
        return splitFrederickson(boustrophedon(anchors), cutters);
    }
    const int width = std::min(m, 180);
    std::vector<std::vector<int>> cost(static_cast<size_t>(width),
                                       std::vector<int>(static_cast<size_t>(width), 0));
    for (int left = 0; left < width; ++left) {
        std::map<int, std::vector<Point>> block;
        for (int right = left; right < width; ++right) {
            block[strips[static_cast<size_t>(right)].first] =
                strips[static_cast<size_t>(right)].second;
            cost[static_cast<size_t>(left)][static_cast<size_t>(right)] =
                closedLength(boustrophedonColumns(block));
        }
    }
    const int parts = std::min(cutters, width);
    const int inf = std::numeric_limits<int>::max() / 4;
    std::vector<std::vector<int>> dp(static_cast<size_t>(parts + 1),
                                     std::vector<int>(static_cast<size_t>(width + 1), inf));
    std::vector<std::vector<int>> prev(static_cast<size_t>(parts + 1),
                                       std::vector<int>(static_cast<size_t>(width + 1), -1));
    dp[0][0] = 0;
    for (int p = 1; p <= parts; ++p) {
        for (int j = 1; j <= width; ++j) {
            for (int i = 0; i < j; ++i) {
                if (dp[static_cast<size_t>(p - 1)][static_cast<size_t>(i)] >= inf) continue;
                const int candidate =
                    std::max(dp[static_cast<size_t>(p - 1)][static_cast<size_t>(i)],
                             cost[static_cast<size_t>(i)][static_cast<size_t>(j - 1)]);
                if (candidate < dp[static_cast<size_t>(p)][static_cast<size_t>(j)]) {
                    dp[static_cast<size_t>(p)][static_cast<size_t>(j)] = candidate;
                    prev[static_cast<size_t>(p)][static_cast<size_t>(j)] = i;
                }
            }
        }
    }
    std::vector<std::pair<int, int>> ranges;
    int cutterIndex = parts;
    int end = width;
    while (cutterIndex > 0 && end > 0) {
        const int begin = prev[static_cast<size_t>(cutterIndex)][static_cast<size_t>(end)];
        if (begin < 0) break;
        ranges.push_back({begin, end - 1});
        end = begin;
        --cutterIndex;
    }
    std::reverse(ranges.begin(), ranges.end());
    std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
    for (size_t i = 0; i < ranges.size() && i < groups.size(); ++i) {
        std::map<int, std::vector<Point>> block;
        for (int c = ranges[i].first; c <= ranges[i].second; ++c)
            block[strips[static_cast<size_t>(c)].first] = strips[static_cast<size_t>(c)].second;
        groups[i] = boustrophedonColumns(block);
    }
    if (m > width) {
        std::vector<Point> tail;
        for (int i = width; i < m; ++i)
            tail.insert(tail.end(), strips[static_cast<size_t>(i)].second.begin(),
                        strips[static_cast<size_t>(i)].second.end());
        auto extra = splitFrederickson(boustrophedon(tail), 1);
        if (!extra.empty() && !groups.empty())
            groups.back().insert(groups.back().end(), extra[0].begin(), extra[0].end());
    }
    return groups;
}

std::vector<std::vector<Point>> TourConstruction::columnGenerationTours(
    const std::vector<Point>& anchors, int k,
    const std::chrono::steady_clock::time_point& start, double limit) {
    const int cutters = std::max(k, 1);
    if (anchors.empty()) return std::vector<std::vector<Point>>(static_cast<size_t>(cutters));
    const auto treeTours = mstc(anchors, cutters);
    const auto splitTours = splitFrederickson(boustrophedon(anchors), cutters);
    auto lengthOf = [](const std::vector<std::vector<Point>>& groups) {
        int result = 0;
        for (const auto& group : groups) result = std::max(result, closedLength(group));
        return result;
    };
    int lo = std::max(1, static_cast<int>(anchors.size() + static_cast<size_t>(cutters) - 1U) /
                             cutters);
    int hi = std::max(lengthOf(splitTours), lengthOf(treeTours));
    const auto index = indexMap(anchors);
    auto growOnce = [&](int budget, std::unordered_set<Point, PointHash>& uncovered) {
        std::vector<Point> grown;
        if (uncovered.empty()) return grown;
        const Point seed = *uncovered.begin();
        std::queue<Point> queue;
        std::unordered_set<Point, PointHash> seen;
        queue.push(seed);
        seen.insert(seed);
        while (!queue.empty() && !timedOut(start, limit)) {
            const Point u = queue.front();
            queue.pop();
            grown.push_back(u);
            if (closedLength(boustrophedon(grown)) > budget) {
                grown.pop_back();
                break;
            }
            for (const Point delta : kNeighbor) {
                const Point next = u + delta;
                if (uncovered.count(next) == 0U || seen.count(next) != 0U) continue;
                if (index.count(next) == 0U) continue;
                seen.insert(next);
                queue.push(next);
            }
        }
        if (grown.empty()) grown.push_back(seed);
        return grown;
    };
    auto feasible = [&](int budget) {
        std::unordered_set<Point, PointHash> uncovered(anchors.begin(), anchors.end());
        int used = 0;
        while (!uncovered.empty()) {
            if (used >= cutters) return false;
            if (timedOut(start, limit)) return true;
            const auto grown = growOnce(budget, uncovered);
            for (const Point point : grown) uncovered.erase(point);
            ++used;
        }
        return true;
    };
    while (lo < hi && !timedOut(start, limit)) {
        const int mid = lo + (hi - lo) / 2;
        if (feasible(mid))
            hi = mid;
        else
            lo = mid + 1;
    }
    std::unordered_set<Point, PointHash> uncovered(anchors.begin(), anchors.end());
    std::vector<std::vector<Point>> groups(static_cast<size_t>(cutters));
    for (int i = 0; i < cutters && !uncovered.empty(); ++i) {
        const auto grown = growOnce(hi, uncovered);
        for (const Point point : grown) uncovered.erase(point);
        groups[static_cast<size_t>(i)] = boustrophedon(grown);
    }
    if (!uncovered.empty()) {
        std::vector<Point> leftover(uncovered.begin(), uncovered.end());
        groups.back().insert(groups.back().end(), leftover.begin(), leftover.end());
        groups.back() = boustrophedon(groups.back());
    }
    const int grownLength = lengthOf(groups);
    if (lengthOf(splitTours) < grownLength && lengthOf(splitTours) <= lengthOf(treeTours))
        return splitTours;
    if (lengthOf(treeTours) < grownLength) return treeTours;
    return groups;
}

Solution TourConstruction::improveLns(const Problem& problem, Solution solution,
                                      const std::chrono::steady_clock::time_point& start,
                                      double limit) {
    auto best = solution;
    std::string error;
    if (!best.validate(problem, &error)) return best;
    int bestSpan = 0;
    for (const Tour& tour : best.tours)
        bestSpan = std::max(bestSpan, closedLength(tour.points));
    std::mt19937 rng(2027);
    int iteration = 0;
    while (!timedOut(start, limit) && iteration < 250) {
        ++iteration;
        if (best.tours.empty()) break;
        size_t longest = 0;
        size_t shortest = 0;
        for (size_t i = 1; i < best.tours.size(); ++i) {
            if (closedLength(best.tours[i].points) > closedLength(best.tours[longest].points))
                longest = i;
            if (closedLength(best.tours[i].points) < closedLength(best.tours[shortest].points))
                shortest = i;
        }
        Solution candidate = best;
        if (iteration % 4 == 0) {
            std::vector<Point> giant;
            for (const Tour& tour : best.tours)
                giant.insert(giant.end(), tour.points.begin(), tour.points.end());
            giant = compactPath(giant);
            const int rotate = static_cast<int>(
                rng() % static_cast<unsigned>(std::max<int>(closedLength(giant), 1)));
            auto groups = splitFrederickson(giant, problem.numberOfCutters);
            if (!groups.empty() && rotate > 0 && !groups[0].empty())
                std::rotate(groups.begin(), groups.begin() + 1, groups.end());
            candidate = makeSolution(problem, groups);
        } else if (longest != shortest && candidate.tours[longest].points.size() > 3U) {
            auto& src = candidate.tours[longest].points;
            auto& dst = candidate.tours[shortest].points;
            const int n = static_cast<int>(src.size());
            const int a = static_cast<int>(rng() % static_cast<unsigned>(n - 1));
            const int b = std::min(n, a + 1 + static_cast<int>(rng() % 4U));
            std::vector<Point> moved(src.begin() + a, src.begin() + b);
            src.erase(src.begin() + a, src.begin() + b);
            if (src.empty()) src.push_back(moved.front());
            dst.insert(dst.end(), moved.begin(), moved.end());
            src = compactPath(src);
            dst = compactPath(dst);
        } else {
            auto& pts = candidate.tours[longest].points;
            if (pts.size() > 4U) {
                const int n = static_cast<int>(pts.size());
                int i = static_cast<int>(rng() % static_cast<unsigned>(n - 3));
                int j = i + 2 + static_cast<int>(rng() % static_cast<unsigned>(n - i - 2));
                if (j < n) std::reverse(pts.begin() + i, pts.begin() + j);
                pts = compactPath(pts);
            }
        }
        if (!candidate.validate(problem, &error)) continue;
        int span = 0;
        for (const Tour& tour : candidate.tours)
            span = std::max(span, closedLength(tour.points));
        if (span < bestSpan) {
            best = candidate;
            bestSpan = span;
        }
    }
    return best;
}

int TourConstruction::closedLength(const std::vector<Point>& points) {
    if (points.size() <= 1U) return 0;
    int length = 0;
    for (size_t i = 0; i < points.size(); ++i)
        length += points[i].manhattanDistance(points[(i + 1) % points.size()]);
    return length;
}

bool TourConstruction::timedOut(const std::chrono::steady_clock::time_point& start,
                                double limit) {
    return limit >= 0 && std::chrono::duration<double>(
                             std::chrono::steady_clock::now() - start)
                                 .count() >= limit;
}

int TourConstruction::areaLowerBound(const Problem& problem) {
    const int cells = static_cast<int>(problem.regionCells().size());
    const int cutter = std::max(1, static_cast<int>(problem.cutterCells().size()));
    const int k = std::max(1, problem.numberOfCutters);
    return (cells + k * cutter - 1) / (k * cutter);
}

}  // namespace cgshop2027
