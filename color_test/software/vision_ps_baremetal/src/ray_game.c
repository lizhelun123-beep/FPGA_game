#include "ray_game.h"

#include <float.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#define RAY_EPSILON 1.0f
#define RAY_SOURCE_OFFSET 3.0f
#define RAY_MIN_DIRECTION 1.0e-6f
#define RAY_PARALLEL_EPSILON 1.0e-6f

typedef struct {
    int object_index;
    float distance;
    RayPoint point;
    RayPoint normal;
    float local_u;
    int side;
} RayHit;

static float dot(RayPoint first, RayPoint second)
{
    return first.x * second.x + first.y * second.y;
}

static RayPoint add_scaled(RayPoint point, RayPoint direction, float scale)
{
    RayPoint result;
    result.x = point.x + direction.x * scale;
    result.y = point.y + direction.y * scale;
    return result;
}

static int normalize(RayPoint *point)
{
    float magnitude;
    if (!point) return 0;
    magnitude = sqrtf(dot(*point, *point));
    if (magnitude <= RAY_MIN_DIRECTION) return 0;
    point->x /= magnitude;
    point->y /= magnitude;
    return 1;
}

static RayObjectType object_type_from_vision(VisionType type)
{
    switch (type) {
    case VISION_MIRROR: return RAY_OBJECT_MIRROR;
    case VISION_PORTAL_A: return RAY_OBJECT_PORTAL_A;
    case VISION_PORTAL_B: return RAY_OBJECT_PORTAL_B;
    case VISION_TARGET: return RAY_OBJECT_TARGET;
    case VISION_SOURCE: return RAY_OBJECT_SOURCE;
    case VISION_WALL: return RAY_OBJECT_WALL;
    default: return RAY_OBJECT_WALL;
    }
}

int ray_game_scene_from_detections(const VisionDetection *detections, int count,
                                   SceneObject *objects, int capacity)
{
    int index;
    if (count < 0 || capacity < 0 || (count && !detections) ||
        (capacity && !objects))
        return -1;
    if (count > capacity) count = capacity;
    for (index = 0; index < count; ++index) {
        const VisionDetection *detection = &detections[index];
        SceneObject *object = &objects[index];
        float bbox_long = detection->bbox_w > detection->bbox_h ?
                          (float)detection->bbox_w : (float)detection->bbox_h;
        float bbox_short = detection->bbox_w < detection->bbox_h ?
                           (float)detection->bbox_w : (float)detection->bbox_h;
        float radians;
        memset(object, 0, sizeof(*object));
        object->type = object_type_from_vision(detection->type);
        object->center.x = detection->geometry_center_x != 0.0f ||
                           detection->center_x == 0 ?
                           detection->geometry_center_x :
                           (float)detection->center_x;
        object->center.y = detection->geometry_center_y != 0.0f ||
                           detection->center_y == 0 ?
                           detection->geometry_center_y :
                           (float)detection->center_y;
        object->axis.x = detection->axis_x;
        object->axis.y = detection->axis_y;
        if (!normalize(&object->axis)) {
            radians = (float)detection->angle_deg *
                      3.14159265358979323846f / 180.0f;
            object->axis.x = cosf(radians);
            object->axis.y = sinf(radians);
        }
        object->length = detection->major_length > RAY_EPSILON ?
                         detection->major_length : bbox_long;
        object->width = detection->minor_width > RAY_EPSILON ?
                        detection->minor_width : bbox_short;
        if (object->type == RAY_OBJECT_TARGET) {
            object->length = bbox_short;
            object->width = bbox_short;
        } else if (object->type == RAY_OBJECT_MIRROR) {
            /* Detection encloses the yellow carrier; reflection uses the
             * finite white stroke between the black endpoint marks. */
            object->length *= VISION_MIRROR_SURFACE_LENGTH_RATIO;
        }
        if (object->length < RAY_EPSILON) object->length = RAY_EPSILON;
        if (object->width < RAY_EPSILON) object->width = RAY_EPSILON;
        object->source_tip.x = (float)detection->source_tip_x;
        object->source_tip.y = (float)detection->source_tip_y;
        object->source_direction.x = detection->source_direction_x;
        object->source_direction.y = detection->source_direction_y;
        object->direction_valid = detection->direction_valid &&
                                  normalize(&object->source_direction);
    }
    return count;
}

static int update_slab(float origin, float direction, float half_extent,
                       RayPoint negative_normal, RayPoint positive_normal,
                       float *near_distance, float *far_distance,
                       RayPoint *near_normal, RayPoint *far_normal)
{
    float first;
    float second;
    RayPoint first_normal = negative_normal;
    RayPoint second_normal = positive_normal;
    if (fabsf(direction) <= RAY_PARALLEL_EPSILON)
        return fabsf(origin) <= half_extent;
    first = (-half_extent-origin) / direction;
    second = (half_extent-origin) / direction;
    if (first > second) {
        float temporary = first;
        RayPoint temporary_normal = first_normal;
        first = second;
        second = temporary;
        first_normal = second_normal;
        second_normal = temporary_normal;
    }
    if (first > *near_distance) {
        *near_distance = first;
        *near_normal = first_normal;
    }
    if (second < *far_distance) {
        *far_distance = second;
        *far_normal = second_normal;
    }
    return *near_distance <= *far_distance;
}

static int ray_obb_intersection(RayPoint origin, RayPoint direction,
                                const SceneObject *object,
                                int side_faces_only, RayHit *hit)
{
    RayPoint normal = {-object->axis.y, object->axis.x};
    RayPoint negative_axis = {-object->axis.x, -object->axis.y};
    RayPoint negative_normal = {-normal.x, -normal.y};
    RayPoint relative = {origin.x-object->center.x, origin.y-object->center.y};
    float local_origin_x = dot(relative, object->axis);
    float local_origin_y = dot(relative, normal);
    float local_direction_x = dot(direction, object->axis);
    float local_direction_y = dot(direction, normal);
    float near_distance = -FLT_MAX;
    float far_distance = FLT_MAX;
    RayPoint near_normal = {0.0f, 0.0f};
    RayPoint far_normal = {0.0f, 0.0f};
    float distance;
    RayPoint point;
    if (!update_slab(local_origin_x, local_direction_x, 0.5f*object->length,
                     negative_axis, object->axis, &near_distance,
                     &far_distance, &near_normal, &far_normal) ||
        !update_slab(local_origin_y, local_direction_y, 0.5f*object->width,
                     negative_normal, normal, &near_distance, &far_distance,
                     &near_normal, &far_normal) ||
        far_distance <= RAY_EPSILON)
        return 0;
    if (near_distance > RAY_EPSILON) {
        distance = near_distance;
        hit->normal = near_normal;
    } else {
        distance = far_distance;
        hit->normal = far_normal;
    }
    if (side_faces_only && fabsf(dot(hit->normal, normal)) < 0.5f) return 0;
    point = add_scaled(origin, direction, distance);
    hit->distance = distance;
    hit->point = point;
    hit->local_u = dot((RayPoint){point.x-object->center.x,
                                 point.y-object->center.y}, object->axis) /
                   (0.5f*object->length);
    if (hit->local_u < -1.0f) hit->local_u = -1.0f;
    if (hit->local_u > 1.0f) hit->local_u = 1.0f;
    hit->side = dot(hit->normal, normal) >= 0.0f ? 1 : -1;
    return 1;
}

static int ray_target_intersection(RayPoint origin, RayPoint direction,
                                   const SceneObject *object, float *distance)
{
    float radius = 0.5f * fminf(object->length, object->width);
    RayPoint relative = {origin.x-object->center.x, origin.y-object->center.y};
    float b;
    float c;
    float discriminant;
    float first;
    float second;
    if (radius <= RAY_EPSILON) return 0;
    b = 2.0f * dot(relative, direction);
    c = dot(relative, relative) - radius*radius;
    discriminant = b*b - 4.0f*c;
    if (discriminant < 0.0f) return 0;
    discriminant = sqrtf(discriminant);
    first = (-b-discriminant) * 0.5f;
    second = (-b+discriminant) * 0.5f;
    if (first > RAY_EPSILON) {
        *distance = first;
        return 1;
    }
    if (second > RAY_EPSILON) {
        *distance = second;
        return 1;
    }
    return 0;
}

static float cross(RayPoint first, RayPoint second)
{
    return first.x * second.y - first.y * second.x;
}

static int ray_mirror_intersection(RayPoint origin, RayPoint direction,
                                   const SceneObject *object, RayHit *hit)
{
    RayPoint axis = object->axis;
    RayPoint relative;
    RayPoint normal;
    float denominator;
    float distance;
    float local;
    if (!normalize(&axis) || object->length <= RAY_EPSILON) return 0;
    relative.x = object->center.x-origin.x;
    relative.y = object->center.y-origin.y;
    denominator = cross(direction, axis);
    if (fabsf(denominator) <= RAY_PARALLEL_EPSILON) return 0;
    distance = cross(relative, axis) / denominator;
    local = cross(relative, direction) / denominator;
    if (distance <= RAY_EPSILON || fabsf(local) > 0.5f*object->length)
        return 0;
    normal.x = -axis.y;
    normal.y = axis.x;
    if (dot(direction, normal) > 0.0f) {
        normal.x = -normal.x;
        normal.y = -normal.y;
    }
    hit->distance = distance;
    hit->point = add_scaled(origin, direction, distance);
    hit->normal = normal;
    hit->local_u = local/(0.5f*object->length);
    hit->side = 0;
    return 1;
}

static int intersect_object(RayPoint origin, RayPoint direction,
                            const SceneObject *object, RayHit *hit)
{
    switch (object->type) {
    case RAY_OBJECT_MIRROR:
        return ray_mirror_intersection(origin, direction, object, hit);
    case RAY_OBJECT_PORTAL_A:
    case RAY_OBJECT_PORTAL_B:
        return ray_obb_intersection(origin, direction, object, 1, hit);
    case RAY_OBJECT_WALL:
        return ray_obb_intersection(origin, direction, object, 0, hit);
    case RAY_OBJECT_TARGET:
        return ray_target_intersection(origin, direction, object,
                                       &hit->distance);
    case RAY_OBJECT_SOURCE:
    default:
        return 0;
    }
}

static int find_pair(const SceneObject *objects, int count, int entry_index)
{
    RayObjectType wanted = objects[entry_index].type == RAY_OBJECT_PORTAL_A ?
                           RAY_OBJECT_PORTAL_B : RAY_OBJECT_PORTAL_A;
    int index;
    int pair = -1;
    int entry_count = 0;
    for (index = 0; index < count; ++index) {
        if (objects[index].type == objects[entry_index].type) entry_count++;
        if (objects[index].type == wanted) {
            if (pair >= 0) return -1;
            pair = index;
        }
    }
    return entry_count == 1 ? pair : -1;
}

static float boundary_distance(RayPoint origin, RayPoint direction,
                               float width, float height)
{
    float best = FLT_MAX;
    float candidate;
    float coordinate;
    if (direction.x > RAY_MIN_DIRECTION) {
        candidate = (width-1.0f-origin.x) / direction.x;
        coordinate = origin.y + candidate*direction.y;
        if (candidate >= 0.0f && coordinate >= 0.0f && coordinate <= height-1.0f)
            best = candidate;
    } else if (direction.x < -RAY_MIN_DIRECTION) {
        candidate = -origin.x / direction.x;
        coordinate = origin.y + candidate*direction.y;
        if (candidate >= 0.0f && coordinate >= 0.0f && coordinate <= height-1.0f)
            best = candidate;
    }
    if (direction.y > RAY_MIN_DIRECTION) {
        candidate = (height-1.0f-origin.y) / direction.y;
        coordinate = origin.x + candidate*direction.x;
        if (candidate >= 0.0f && candidate < best &&
            coordinate >= 0.0f && coordinate <= width-1.0f)
            best = candidate;
    } else if (direction.y < -RAY_MIN_DIRECTION) {
        candidate = -origin.y / direction.y;
        coordinate = origin.x + candidate*direction.x;
        if (candidate >= 0.0f && candidate < best &&
            coordinate >= 0.0f && coordinate <= width-1.0f)
            best = candidate;
    }
    return best;
}

static void append_segment(RayGameResult *result, RayPoint start, RayPoint end)
{
    if (result->segment_count >= RAY_GAME_MAX_SEGMENTS) return;
    result->segments[result->segment_count].start = start;
    result->segments[result->segment_count].end = end;
    result->segment_count++;
}

int ray_game_trace(const SceneObject *objects, int count,
                   float frame_width, float frame_height,
                   RayGameResult *result)
{
    RayPoint origin;
    RayPoint direction;
    int source_index = -1;
    int last_hit = -1;
    int index;
    if (!result) return -1;
    memset(result, 0, sizeof(*result));
    result->termination = RAY_GAME_INVALID_INPUT;
    if (count < 0 || frame_width <= 1.0f || frame_height <= 1.0f ||
        (count && !objects))
        return -1;
    for (index = 0; index < count; ++index) {
        if (objects[index].type == RAY_OBJECT_SOURCE &&
            objects[index].direction_valid) {
            source_index = index;
            break;
        }
    }
    if (source_index < 0) {
        result->termination = RAY_GAME_NO_SOURCE;
        return 0;
    }
    direction = objects[source_index].source_direction;
    if (!normalize(&direction)) {
        result->termination = RAY_GAME_NO_SOURCE;
        return 0;
    }
    origin = add_scaled(objects[source_index].source_tip, direction,
                        RAY_SOURCE_OFFSET);
    for (;;) {
        RayHit nearest;
        float edge_distance;
        memset(&nearest, 0, sizeof(nearest));
        nearest.object_index = -1;
        nearest.distance = FLT_MAX;
        for (index = 0; index < count; ++index) {
            RayHit candidate;
            memset(&candidate, 0, sizeof(candidate));
            candidate.object_index = index;
            if (objects[index].type == RAY_OBJECT_SOURCE ||
                !intersect_object(origin, direction, &objects[index], &candidate))
                continue;
            if (index == last_hit &&
                candidate.distance <= 4.0f*RAY_EPSILON) continue;
            if (candidate.distance < nearest.distance) {
                nearest = candidate;
            }
        }
        edge_distance = boundary_distance(origin, direction,
                                          frame_width, frame_height);
        if (nearest.object_index < 0 || edge_distance < nearest.distance) {
            if (edge_distance != FLT_MAX)
                append_segment(result, origin,
                               add_scaled(origin, direction, edge_distance));
            result->termination = RAY_GAME_BOUNDARY;
            return 0;
        }
        nearest.point = add_scaled(origin, direction, nearest.distance);
        append_segment(result, origin, nearest.point);
        if (result->hit_count < RAY_GAME_MAX_INTERACTIONS)
            result->hit_types[result->hit_count++] =
                objects[nearest.object_index].type;
        switch (objects[nearest.object_index].type) {
        case RAY_OBJECT_WALL:
            result->termination = RAY_GAME_WALL;
            return 0;
        case RAY_OBJECT_TARGET:
            result->success = 1;
            result->termination = RAY_GAME_TARGET;
            return 0;
        case RAY_OBJECT_MIRROR: {
            float projection = dot(direction, nearest.normal);
            direction.x -= 2.0f*projection*nearest.normal.x;
            direction.y -= 2.0f*projection*nearest.normal.y;
            (void)normalize(&direction);
            last_hit = nearest.object_index;
            origin = add_scaled(nearest.point, direction, RAY_EPSILON);
            result->interaction_count++;
            break;
        }
        case RAY_OBJECT_PORTAL_A:
        case RAY_OBJECT_PORTAL_B: {
            int pair_index = find_pair(objects, count, nearest.object_index);
            RayPoint u_in;
            RayPoint v_in;
            RayPoint u_out;
            RayPoint v_out;
            RayPoint exit_point;
            float along;
            float across;
            int exit_side;
            if (pair_index < 0) {
                result->termination = RAY_GAME_MISSING_PORTAL;
                return 0;
            }
            u_in = objects[nearest.object_index].axis;
            u_out = objects[pair_index].axis;
            if (!normalize(&u_in) || !normalize(&u_out)) {
                result->termination = RAY_GAME_INVALID_INPUT;
                return -1;
            }
            v_in.x = -u_in.y;
            v_in.y = u_in.x;
            v_out.x = -u_out.y;
            v_out.y = u_out.x;
            along = dot(direction, u_in);
            across = dot(direction, v_in);
            exit_side = -nearest.side;
            direction.x = along*u_out.x + across*v_out.x;
            direction.y = along*u_out.y + across*v_out.y;
            if (!normalize(&direction)) {
                result->termination = RAY_GAME_INVALID_INPUT;
                return -1;
            }
            last_hit = pair_index;
            exit_point = add_scaled(objects[pair_index].center,
                                    u_out,
                                    nearest.local_u*0.5f*
                                    objects[pair_index].length);
            exit_point = add_scaled(exit_point, v_out,
                                    (float)exit_side*
                                    0.5f*objects[pair_index].width);
            origin = add_scaled(exit_point, direction, RAY_EPSILON);
            result->interaction_count++;
            break;
        }
        case RAY_OBJECT_SOURCE:
        default:
            result->termination = RAY_GAME_INVALID_INPUT;
            return -1;
        }
        if (result->interaction_count >= RAY_GAME_MAX_INTERACTIONS) {
            result->termination = RAY_GAME_MAX_INTERACTIONS_REACHED;
            return 0;
        }
    }
}

#define RAY_STABLE_ENDPOINT_DISTANCE 4.0f
#define RAY_STABLE_DIRECTION_DOT 0.99939082701909573001f

static const SceneObject *level_source(const SceneObject *objects, int count)
{
    int index;
    if (count < 0 || (count && !objects)) return NULL;
    for (index = 0; index < count; ++index)
        if (objects[index].type == RAY_OBJECT_SOURCE &&
            objects[index].direction_valid)
            return &objects[index];
    return NULL;
}

static int ray_topology_equal(const RayGameResult *first,
                              const RayGameResult *second)
{
    int index;
    if (first->segment_count != second->segment_count ||
        first->interaction_count != second->interaction_count ||
        first->success != second->success ||
        first->termination != second->termination ||
        first->hit_count != second->hit_count)
        return 0;
    for (index = 0; index < first->hit_count; ++index)
        if (first->hit_types[index] != second->hit_types[index]) return 0;
    return 1;
}

static float point_distance_squared(RayPoint first, RayPoint second)
{
    float dx = first.x-second.x;
    float dy = first.y-second.y;
    return dx*dx+dy*dy;
}

static int segment_geometry_stable(const RaySegment *first,
                                   const RaySegment *second)
{
    RayPoint first_direction = {first->end.x-first->start.x,
                                first->end.y-first->start.y};
    RayPoint second_direction = {second->end.x-second->start.x,
                                 second->end.y-second->start.y};
    float limit = RAY_STABLE_ENDPOINT_DISTANCE*RAY_STABLE_ENDPOINT_DISTANCE;
    if (point_distance_squared(first->start, second->start) > limit ||
        point_distance_squared(first->end, second->end) > limit)
        return 0;
    if (!normalize(&first_direction) || !normalize(&second_direction))
        return 0;
    return dot(first_direction, second_direction) >= RAY_STABLE_DIRECTION_DOT;
}

static int ray_stable_equal(const RayGameResult *first,
                            const RayGameResult *second)
{
    int index;
    if (!ray_topology_equal(first, second)) return 0;
    for (index = 0; index < first->segment_count; ++index)
        if (!segment_geometry_stable(&first->segments[index],
                                     &second->segments[index]))
            return 0;
    return 1;
}

static unsigned int commit_current_ray(RayGameLevel *level,
                                       const SceneObject *objects,
                                       int count, float frame_width,
                                       float frame_height)
{
    unsigned int events = 0;
    if (ray_game_trace(objects, count, frame_width, frame_height,
                       &level->candidate_ray) != 0 ||
        level->candidate_ray.segment_count <= 0 ||
        level->candidate_ray.termination == RAY_GAME_NO_SOURCE ||
        level->candidate_ray.termination == RAY_GAME_INVALID_INPUT)
        return RAY_LEVEL_EVENT_CANDIDATE_INVALID;
    level->candidate_invalid = 0;
    if (level->committed_ray_valid &&
        ray_stable_equal(&level->committed_ray, &level->candidate_ray)) {
        if (level->candidate_ray.success && !level->target_reached) {
            level->target_hit_count = RAY_GAME_TARGET_CONFIRM_HITS;
            level->target_reached = 1;
            return RAY_LEVEL_EVENT_TARGET_HIT |
                   RAY_LEVEL_EVENT_TARGET_CONFIRMED;
        }
        return 0;
    }
    if (level->committed_ray_valid &&
        !ray_topology_equal(&level->committed_ray, &level->candidate_ray))
        level->topology_change_count++;
    level->committed_ray = level->candidate_ray;
    level->committed_ray_valid = 1;
    level->candidate_ray_stable_count = 0;
    level->committed_ray_update_count++;
    events |= RAY_LEVEL_EVENT_RAY_COMMITTED;
    if (level->committed_ray.success && !level->target_reached) {
        level->target_hit_count = RAY_GAME_TARGET_CONFIRM_HITS;
        level->target_reached = 1;
        events |= RAY_LEVEL_EVENT_TARGET_HIT |
                  RAY_LEVEL_EVENT_TARGET_CONFIRMED;
    }
    return events;
}

static unsigned int invalid_candidate(RayGameLevel *level)
{
    unsigned int events = 0;
    level->candidate_ray_stable_count = 0;
    if (!level->candidate_invalid)
        events |= RAY_LEVEL_EVENT_CANDIDATE_INVALID;
    level->candidate_invalid = 1;
    return events;
}

static unsigned int clear_missing_source(RayGameLevel *level)
{
    unsigned int events = 0;
    int had_source_or_ray = level->source_locked ||
                            level->source_sample_count > 0 ||
                            level->committed_ray_valid;
    level->source_sample_count = 0;
    level->source_locked = 0;
    memset(&level->locked_source, 0, sizeof(level->locked_source));
    memset(&level->candidate_ray, 0, sizeof(level->candidate_ray));
    memset(&level->committed_ray, 0, sizeof(level->committed_ray));
    level->committed_ray_valid = 0;
    level->candidate_ray_stable_count = 0;
    level->target_hit_count = 0;
    level->target_reached = 0;
    level->candidate_invalid = 0;
    if (had_source_or_ray) {
        level->source_clear_count++;
        events |= RAY_LEVEL_EVENT_LEVEL_CLEARED;
    }
    if (level->state != RAY_LEVEL_ACQUIRE_SOURCE) {
        level->state = RAY_LEVEL_ACQUIRE_SOURCE;
        events |= RAY_LEVEL_EVENT_STATE_CHANGED;
    }
    return events;
}

void ray_game_level_reset(RayGameLevel *level)
{
    if (!level) return;
    memset(level, 0, sizeof(*level));
    level->state = RAY_LEVEL_INIT;
}

unsigned int ray_game_level_update(RayGameLevel *level,
                                   const SceneObject *objects, int count,
                                   int scene_valid,
                                   float frame_width, float frame_height)
{
    unsigned int events = 0;
    const SceneObject *source;
    if (!level) return RAY_LEVEL_EVENT_CANDIDATE_INVALID;
    if (level->state == RAY_LEVEL_INIT) {
        level->state = RAY_LEVEL_ACQUIRE_SOURCE;
        events |= RAY_LEVEL_EVENT_STATE_CHANGED;
    }
    if (!scene_valid) return events | invalid_candidate(level);
    source = level_source(objects, count);
    if (!source) return events | clear_missing_source(level);
    if (!level->source_locked) {
        events |= RAY_LEVEL_EVENT_SOURCE_SAMPLE;
        events |= RAY_LEVEL_EVENT_SOURCE_LOCKED;
    }
    level->source_samples[0] = *source;
    level->source_sample_count = 1;
    level->locked_source = *source;
    level->source_locked = 1;
    events |= commit_current_ray(level, objects, count,
                                 frame_width, frame_height);
    if (events & RAY_LEVEL_EVENT_CANDIDATE_INVALID)
        return (events & ~RAY_LEVEL_EVENT_CANDIDATE_INVALID) |
               invalid_candidate(level);
    if (level->state != RAY_LEVEL_ACTIVE) {
        level->state = RAY_LEVEL_ACTIVE;
        events |= RAY_LEVEL_EVENT_STATE_CHANGED;
    }
    return events;
}

const RayGameResult *ray_game_level_display_ray(const RayGameLevel *level)
{
    if (!level || !level->committed_ray_valid ||
        level->committed_ray.segment_count <= 0)
        return NULL;
    return &level->committed_ray;
}

const char *ray_game_level_state_name(RayGameLevelState state)
{
    switch (state) {
    case RAY_LEVEL_INIT: return "INIT";
    case RAY_LEVEL_ACQUIRE_SOURCE: return "ACQUIRE_SOURCE";
    case RAY_LEVEL_SOURCE_LOCKED: return "SOURCE_LOCKED";
    case RAY_LEVEL_ACTIVE: return "ACTIVE";
    case RAY_LEVEL_TARGET_CONFIRM: return "TARGET_CONFIRM";
    case RAY_LEVEL_TRANSITION: return "TRANSITION";
    default: return "UNKNOWN";
    }
}
